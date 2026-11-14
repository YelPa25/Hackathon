"""Command-line interface for the per-modality alert node."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from typing import Iterator

from alerting.adapters.facial import get_facial_config
from alerting.adapters.speech import get_speech_config
from alerting.core.config import AlertConfig
from alerting.core.node import AlertNode


def tail_file(filepath: str, speedup: float = 1.0) -> Iterator[str]:
    """Yield lines from file, following as new lines are appended."""
    with open(filepath, "r", encoding="utf-8") as f:
        while True:
            line = f.readline()
            if line:
                yield line
                if speedup > 0:
                    time.sleep(max(0.001, 1.0 / speedup))
            else:
                time.sleep(0.1)


def read_static_file(filepath: str, speedup: float = 1.0) -> Iterator[str]:
    """Yield lines from file once with simulated playback speedup."""
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield line
                if speedup > 0 and speedup < 1000.0:
                    # e.g., 30s window replayed with speedup=30 -> 1s delay
                    delay = max(0.001, 2.0 / speedup)
                    time.sleep(delay)


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Per-modality robust statistical alerting node."
    )
    parser.add_argument(
        "--modality",
        type=str,
        required=True,
        choices=["facial", "speech"],
        help="Input modality stream: 'facial' or 'speech'.",
    )
    parser.add_argument(
        "--in",
        dest="input_file",
        type=str,
        required=True,
        help="Path to incoming extractor JSONL file.",
    )
    parser.add_argument(
        "--out",
        dest="output_file",
        type=str,
        default="alerts.jsonl",
        help="Path to output alerts JSONL file (default: alerts.jsonl).",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Optional path to custom YAML or JSON config file.",
    )
    parser.add_argument(
        "--subject",
        type=str,
        default="astronaut_1",
        help="Subject identifier (default: astronaut_1).",
    )
    parser.add_argument(
        "--follow",
        action="store_true",
        default=False,
        help="Follow/tail the input file continuously as extractor appends to it.",
    )
    parser.add_argument(
        "--speedup",
        type=float,
        default=1.0,
        help="Playback speed multiplier for replaying recorded files (default: 1.0).",
    )
    parser.add_argument(
        "--adapt",
        action="store_true",
        default=False,
        help="Enable slow EWMA baseline adaptation during normal state (off by default).",
    )
    parser.add_argument(
        "--state-file",
        type=str,
        default=None,
        help="Path to persist/load node state across restarts (default: .alert_state_<modality>.json).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help="Clear any existing persisted state file and recalibrate.",
    )

    args = parser.parse_args()

    # Determine state file path
    state_file = args.state_file or f".alert_state_{args.modality}.json"
    if args.reset and os.path.exists(state_file):
        os.remove(state_file)
        print(f"Cleared existing state file: {state_file}")

    # Load or initialize config
    if args.config:
        config = AlertConfig.from_file(args.config)
    else:
        config = (
            get_facial_config()
            if args.modality == "facial"
            else get_speech_config()
        )

    # Initialize or resume AlertNode
    if os.path.exists(state_file) and not args.reset:
        print(f"Resuming node from persisted state: {state_file}")
        node = AlertNode.load_state(state_file)
        # Update run-time flags
        node.adapt = args.adapt
        node.subject_id = args.subject
    else:
        node = AlertNode(config=config, subject_id=args.subject, adapt=args.adapt)

    if not os.path.exists(args.input_file) and not args.follow:
        print(f"Error: Input file '{args.input_file}' not found.", file=sys.stderr)
        sys.exit(1)

    # Prepare output file
    out_dir = os.path.dirname(args.output_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    out_f = open(args.output_file, "a", encoding="utf-8")

    stop_requested = False

    def sigint_handler(signum, frame):
        nonlocal stop_requested
        print("\nShutdown requested (Ctrl+C). Saving state and exiting...", file=sys.stderr)
        stop_requested = True

    signal.signal(signal.SIGINT, sigint_handler)

    print(
        f"AlertNode initialized: modality={args.modality}, subject={args.subject}, "
        f"input={args.input_file}, output={args.output_file}, follow={args.follow}, adapt={args.adapt}"
    )

    count = 0
    line_iter = (
        tail_file(args.input_file, speedup=args.speedup)
        if args.follow
        else read_static_file(args.input_file, speedup=args.speedup)
    )

    try:
        for line in line_iter:
            if stop_requested:
                break
            line_str = line.strip()
            if not line_str:
                continue

            try:
                record = json.loads(line_str)
            except json.JSONDecodeError:
                continue

            alert_record = node.process_record(record)
            out_f.write(json.dumps(alert_record) + "\n")
            out_f.flush()
            count += 1

            # Print concise one-line summary
            state = alert_record.get("state")
            score = alert_record.get("score", 0.0)
            reason = alert_record.get("reason", "")
            t_iso = alert_record.get("t", "")
            print(f"[{t_iso}] state={state:<11} score={score:.2f} | {reason}")

    finally:
        out_f.close()
        node.save_state(state_file)
        print(f"Processed {count} records. State saved to '{state_file}'.")


if __name__ == "__main__":
    main()
