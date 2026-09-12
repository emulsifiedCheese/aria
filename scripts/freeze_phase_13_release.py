#!/usr/bin/env python3
"""freeze and verify the privacy-safe Phase 13.3 release archive"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from aria.acceptance.release import freeze_release

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs/acceptance/phase_13"),
    )
    args = parser.parse_args(argv)
    result = freeze_release(args.output_root, sys.executable)
    print(json.dumps({
        "release_directory": result["directory"],
        **result["report"],
    }, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())