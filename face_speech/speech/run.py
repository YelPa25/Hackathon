"""Command-line interface for speech analysis and reading passage check-ins."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from typing import Any, Dict, List

import numpy as np
import soundfile as sf

from speech import stream_windows
from speech.audio import record_microphone


STANDARD_PASSAGE = (
    "\"When the sunlight strikes raindrops in the air, they act as a prism and form a rainbow.\n"
    "The rainbow is a division of white light into many beautiful colors. These take the shape\n"
    "of a long round arch, with its path high above, and its two ends apparently beyond the horizon.\n"
    "There is , according to legend, a boiling pot of gold at one end. People look, but no one\n"
    "ever finds it. When a man looks for something beyond his reach, his friends say he is\n"
    "looking for the pot of gold at the end of the rainbow.\"\n"
)


def run_record_checkin(output_path: str, duration_s: float = 30.0) -> None:
    """Show standardized reading passage, record from microphone, and save wav."""
    print("\n" + "=" * 60)
    print("      STANDARDIZED ASTRONAUT CHECK-IN READING PASSAGE      ")
    print("=" * 60)
    print(STANDARD_PASSAGE)
    print("=" * 60)
    input(f"Press Enter when ready to begin recording ({duration_s} seconds)... ")
    print(f"Recording for {duration_s} seconds... Please read the passage aloud at a normal pace.")
    audio = record_microphone(duration_s=duration_s, sample_rate=16000)
    sf.write(output_path, audio, 16000)
    print(f"Recording complete and saved to '{output_path}'.\n")


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Extract voice features, timing, and XLS-R embeddings from speech audio."
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Prompt reading passage, record a standardized check-in audio wav, and save it.",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="sample.wav",
        help="Audio source: 'mic' (or microphone index) or path to .wav file (default: sample.wav).",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["checkin", "continuous"],
        default="continuous",
        help="Operating mode: 'checkin' (whole clip = 1 window) or 'continuous' (sliced into windows).",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=30.0,
        help="Window duration in seconds for continuous mode (default: 30.0).",
    )
    parser.add_argument(
        "--layers",
        type=str,
        default="6,9,12,15,18,24",
        help="Comma-separated XLS-R transformer layers to extract (default: 6,9,12,15,18,24).",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Optional path to output JSONL file to append records.",
    )
    parser.add_argument(
        "--embeddings-npz",
        type=str,
        default=None,
        help="Optional path to save embeddings in compact binary NPZ format.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        choices=["cpu", "cuda"],
        help="Device for PyTorch inference (default: cpu).",
    )

    args = parser.parse_args()

    # Handle --record mode
    if args.record:
        out_wav = args.source if args.source.endswith(".wav") else "checkin_recording.wav"
        run_record_checkin(out_wav, duration_s=args.window)
        # Proceed with analyzing the recorded check-in wav
        args.source = out_wav
        args.mode = "checkin"

    # Parse layers list
    layer_indices = [int(l.strip()) for l in args.layers.split(",") if l.strip().isdigit()]

    out_file = None
    if args.out:
        out_dir = os.path.dirname(args.out)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        out_file = open(args.out, "a", encoding="utf-8")

    npz_embeddings: Dict[str, List[np.ndarray]] = {str(l): [] for l in layer_indices}
    npz_timestamps: List[str] = []

    stop_requested = False

    def sigint_handler(signum: int, frame: Any) -> None:
        nonlocal stop_requested
        print("\nInterrupt received (Ctrl+C). Terminating gracefully (partial window discarded)...", file=sys.stderr)
        stop_requested = True

    signal.signal(signal.SIGINT, sigint_handler)

    print(
        f"Starting speech analysis: source='{args.source}', mode='{args.mode}', "
        f"window={args.window}s, layers={layer_indices}, device={args.device}"
    )

    count = 0
    t0_total = time.time()

    try:
        for record in stream_windows(
            source=args.source,
            mode=args.mode,
            window_s=args.window,
            layers=layer_indices,
            device=args.device,
        ):
            if stop_requested:
                break

            count += 1
            t_iso = record.get("t", "")
            quality = record.get("quality", 0.0)
            valid = record.get("valid", False)
            feats = record.get("features", {})
            speech_rate = feats.get("speech_rate_syll_per_s", 0.0)
            f0_std = feats.get("f0_std", 0.0)

            # Print one-line summary
            print(
                f"[{t_iso}] valid={valid} quality={quality:.2f} "
                f"speech_rate={speech_rate:.2f} syll/s f0_std={f0_std:.2f}"
            )

            # Append to JSONL file
            if out_file is not None:
                out_file.write(json.dumps(record) + "\n")
                out_file.flush()

            # Collect embeddings for compact NPZ export if requested
            if args.embeddings_npz:
                npz_timestamps.append(t_iso)
                for l in layer_indices:
                    vec = record["embedding"]["vectors"].get(str(l), [])
                    npz_embeddings[str(l)].append(np.array(vec, dtype=np.float32))

    finally:
        if out_file is not None:
            out_file.close()

        # Save NPZ file if requested
        if args.embeddings_npz and npz_timestamps:
            save_dict = {
                f"layer_{l}": np.stack(npz_embeddings[str(l)]) for l in layer_indices
            }
            save_dict["timestamps"] = np.array(npz_timestamps)
            np.savez_compressed(args.embeddings_npz, **save_dict)
            print(f"Saved {len(npz_timestamps)} embedding vectors to '{args.embeddings_npz}'.")

        elapsed = time.time() - t0_total
        print(f"Finished processing. Total windows: {count}. Elapsed: {elapsed:.2f} s.")


if __name__ == "__main__":
    main()
