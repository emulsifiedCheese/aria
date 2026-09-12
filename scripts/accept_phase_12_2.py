#!/usr/bin/env python3
"""produce synthetic Phase 12.2 dashboard acceptance record"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from aria.dashboard.acceptance import run_acceptance

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCREENSHOT_DIR = PROJECT_ROOT / "outputs" / "acceptance" / "phase_12_2"
DEFAULT_OUTPUT = DEFAULT_SCREENSHOT_DIR / "acceptance.json"

def build_parser():
    parser = argparse.ArgumentParser(
        description="Run synthetic-only Phase 12.2 dashboard acceptance."
    )
    parser.add_argument("--screenshot-dir", type=Path, default=DEFAULT_SCREENSHOT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser

def main(argv=None):
    args = build_parser().parse_args(argv)
    report = run_acceptance(args.screenshot_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(args.output)
    print(f"Phase 12.2 dashboard acceptance passed: {args.output}")
    return report

if __name__ == "__main__":
    main()