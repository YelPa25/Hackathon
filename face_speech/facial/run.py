"""Command-line interface and real-time capture loop for facial analysis."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from typing import Any, Dict

import cv2

from facial.extractor import LibreFaceExtractor
from facial.windows import WindowAggregator


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Stream facial Action Unit features from webcam or video file."
    )
    parser.add_argument(
        "--source",
        type=str,
        default="0",
        help="Webcam index (e.g. 0) or path to video file (e.g. sample.mp4).",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=30.0,
        help="Aggregation window duration in seconds (default: 30.0).",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=30.0,
        help="Target processing frame rate (default: 15.0).",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Optional path to output JSONL file to append records.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cpu", "cuda", "mps"],
        help="Inference device: 'auto' (default, detects CUDA/MPS/CPU), 'cpu', 'cuda', or 'mps'.",
    )
    parser.add_argument(
        "--weights-dir",
        type=str,
        default="./weights_libreface",
        help="Directory where LibreFace weights are stored.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        default=False,
        help="Display a live preview window with face detection status and FPS.",
    )
    parser.add_argument(
        "--flush-on-exit",
        action="store_true",
        default=False,
        help="Flush and emit the partial window on Ctrl+C or video end (default: discard).",
    )

    args = parser.parse_args()

    # Determine capture source
    cap_source: Any = int(args.source) if args.source.isdigit() else args.source
    is_live = isinstance(cap_source, int)

    # Resolve device if 'auto'
    selected_device = args.device
    if selected_device == "auto":
        import torch
        if torch.cuda.is_available():
            selected_device = "cuda"
        elif torch.backends.mps.is_available():
            selected_device = "mps"
        else:
            selected_device = "cpu"

    cap = cv2.VideoCapture(cap_source)
    if not cap.isOpened():
        print(f"Error: Could not open video source '{args.source}'.", file=sys.stderr)
        sys.exit(1)

    # For live webcam, suggest webcam capture buffer and FPS properties
    if is_live:
        cap.set(cv2.CAP_PROP_FPS, max(30.0, args.fps))

    print(
        f"Initialized source='{args.source}' (live={is_live}), window={args.window}s, "
        f"target_fps={args.fps}, device={selected_device}"
    )

    # Initialize model extractor once
    print("Loading LibreFace models...")
    extractor = LibreFaceExtractor(
        device=selected_device, weights_download_dir=args.weights_dir
    )
    print("Models loaded successfully.")

    frames_per_window = max(1, int(round(args.window * args.fps)))
    aggregator = WindowAggregator(window_size=frames_per_window)

    # Prepare output file if specified
    out_file = None
    if args.out:
        out_dir = os.path.dirname(args.out)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        out_file = open(args.out, "a", encoding="utf-8")

    stop_requested = False

    def sigint_handler(signum: int, frame: Any) -> None:
        nonlocal stop_requested
        print("\nInterrupt received (Ctrl+C). Exiting...", file=sys.stderr)
        stop_requested = True

    signal.signal(signal.SIGINT, sigint_handler)

    def write_record(record: Dict[str, Any]) -> None:
        line = json.dumps(record)
        if out_file is not None:
            out_file.write(line + "\n")
            out_file.flush()
        # Print concise one-line summary
        feats = record.get("features", {})
        expr = feats.get("expressiveness", 0.0)
        pose_std = feats.get("head_pose_std", 0.0)
        act_rate = feats.get("au_activation_rate", 0.0)
        qual = record.get("quality", 0.0)
        valid = record.get("valid", False)
        print(
            f"[{record.get('t')}] quality={qual:.2f} valid={valid} "
            f"expressiveness={expr:.3f} head_pose_std={pose_std:.2f} au_rate={act_rate:.2f}"
        )

    # Timing and FPS measurement
    frame_interval_sec = 1.0 / args.fps
    processed_count = 0
    t_start = time.time()
    last_fps_report = t_start

    # Determine frame step for pre-recorded video
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    if not source_fps or source_fps <= 0 or source_fps > 120:
        source_fps = 30.0
    frame_step = max(1, int(round(source_fps / args.fps)))
    raw_frame_idx = 0

    try:
        while not stop_requested:
            loop_t0 = time.time()

            ret, frame = cap.read()
            if not ret or frame is None:
                # Video ended or camera failure
                break

            if not is_live:
                if raw_frame_idx % frame_step != 0:
                    raw_frame_idx += 1
                    continue
            raw_frame_idx += 1

            # Process frame
            frame_data = extractor.extract_frame(frame)
            processed_count += 1

            window_record = aggregator.add_frame(frame_data)
            if window_record is not None:
                write_record(window_record)

            if args.show:
                disp = frame.copy()
                status_text = "FACE DETECTED" if frame_data.get("face_detected") else "NO FACE"
                color = (0, 255, 0) if frame_data.get("face_detected") else (0, 0, 255)
                cv2.putText(disp, status_text, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                cv2.imshow("Astronaut Monitor (press 'q' or Ctrl+C to stop)", disp)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("\n'q' pressed. Stopping capture...")
                    break

            # Measure real-time FPS
            now = time.time()
            if now - last_fps_report >= 5.0:
                elapsed = now - t_start
                current_fps = processed_count / elapsed if elapsed > 0 else 0.0
                print(f"[STATUS] Processed {processed_count} frames ({current_fps:.2f} fps)")
                last_fps_report = now

            # If webcam, throttle to maintain target fps
            if is_live:
                process_duration = time.time() - loop_t0
                sleep_time = frame_interval_sec - process_duration
                if sleep_time > 0:
                    time.sleep(sleep_time)

    finally:
        # Flush or discard partial window
        if args.flush_on_exit:
            partial_record = aggregator.flush()
            if partial_record is not None:
                print("Flushing partial window on exit...")
                write_record(partial_record)
        else:
            discarded = len(aggregator.buffer)
            if discarded > 0:
                print(f"Discarding partial window with {discarded} frames on exit.")

        cap.release()
        if args.show:
            cv2.destroyAllWindows()
        if out_file is not None:
            out_file.close()

        total_elapsed = time.time() - t_start
        final_fps = processed_count / total_elapsed if total_elapsed > 0 else 0.0
        print(f"Completed. Total frames: {processed_count}, Average processing speed: {final_fps:.2f} fps.")


if __name__ == "__main__":
    main()
