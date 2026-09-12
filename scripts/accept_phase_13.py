#!/usr/bin/env python3
"""create or assess fail-closed Phase 13 acceptance evidence"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from aria.acceptance.phase13 import assess_phase_13, evidence_template

def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write-template", type=Path)
    group.add_argument("--evidence", type=Path)
    parser.add_argument("--output", type=Path)
    return parser

def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.write_template:
        template = evidence_template()
        _write(args.write_template, template)
        print(f"Phase 13 evidence template: {args.write_template}")
        return template
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    result = assess_phase_13(evidence)
    if args.output:
        _write(args.output, result)
    print(json.dumps(result, sort_keys=True))
    return result

if __name__ == "__main__":
    main()