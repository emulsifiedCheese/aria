#!/usr/bin/env python3
"""queue approved local predictions and run one Phase 12.3 delivery pass"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from aria.cloud.firebase_sync import FirebasePredictionSync, FirebaseSyncError

def build_parser():
    parser = argparse.ArgumentParser(
        description="Queue privacy-projected ARIA predictions for Firebase delivery."
    )
    parser.add_argument("--input", required=True, help="local prediction JSONL")
    parser.add_argument(
        "--input-scope",
        required=True,
        choices=("synthetic", "non_research"),
        help="explicitly permitted source provenance",
    )
    parser.add_argument(
        "--queue-only",
        action="store_true",
        help="write the durable local outbox without contacting Firebase",
    )
    return parser

def _records(path):
    try:
        with Path(path).open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise FirebaseSyncError(
                        f"invalid prediction JSON at line {line_number}"
                    ) from error
                if not isinstance(record, dict):
                    raise FirebaseSyncError(
                        f"prediction at line {line_number} is not an object"
                    )
                yield record
    except OSError as error:
        raise FirebaseSyncError("cannot read prediction input") from error

def main(argv=None, *, sync_factory=FirebasePredictionSync):
    args = build_parser().parse_args(argv)
    sync = sync_factory()
    queued = 0
    already_queued = 0
    for record in _records(args.input):
        _, created = sync.enqueue(record)
        queued += int(created)
        already_queued += int(not created)
    result = (
        {
            "delivered": 0,
            "conflicts": 0,
            "pending": len(sync.outbox.pending()),
            "failure": None,
        }
        if args.queue_only
        else sync.flush_due()
    )
    summary = {
        "input_scope": args.input_scope,
        "queued": queued,
        "already_queued": already_queued,
        **result,
    }
    print(json.dumps(summary, sort_keys=True))
    return summary

if __name__ == "__main__":
    main()