#!/usr/bin/env python3
"""list the approved and excluded source sessions used in phase 10.1"""

import argparse
from pathlib import Path

from aria.dataset.source_inventory import (
    apply_approval_decisions,
    scan_source_sessions,
    write_inventory,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "phase_10_1"
    / "source_session_inventory.json"
)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-raw",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw",
    )
    parser.add_argument(
        "--approvals",
        type=Path,
        default=PROJECT_ROOT / "config" / "phase_10_1_source_approvals.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    return parser.parse_args(argv)

def display_inventory(inventory: dict) -> None:
    print(f"INCLUDED - {inventory['review_status'].replace('_', ' ').upper()}")
    for session in inventory["included_sessions"]:
        print(f"\n{session['session_id']}")
        print(
            "  kind                 physical  written  excluded  observed  checks"
        )
        for output in session["outputs"]:
            declared = output["declared"]
            checks = output["checks"]
            result = "PASS" if all(checks.values()) else "REVIEW"
            print(
                f"  {str(output['kind']):20} "
                f"{str(output['physical_record_count']):>8} "
                f"{str(declared['written_record_count']):>8} "
                f"{str(declared['excluded_record_count']):>9} "
                f"{str(declared['observed_record_count']):>9}  {result}"
            )
        incident_count = len(session["incident_ids"])
        print(
            f"  incidents: {incident_count}; manifest review: "
            f"{session['review_status'].upper()}"
        )

    print("\nEXCLUDED")
    for session in inventory["excluded_sessions"]:
        print(f"  {session['session_id']}: {session['exclusion_reason']}")

def main(argv=None) -> None:
    args = parse_args(argv)
    inventory = scan_source_sessions(args.data_raw)
    if args.approvals.is_file():
        apply_approval_decisions(inventory, args.approvals)
    write_inventory(inventory, args.output)
    display_inventory(inventory)
    print(f"\nWrote review inventory to {args.output}")
    print("No source manifest or session record was modified.")


if __name__ == "__main__":
    main()
