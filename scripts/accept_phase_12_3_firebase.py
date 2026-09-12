#!/usr/bin/env python3
"""guarded synthetic live acceptance for Phase 12.3 Firebase delivery"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from aria.cloud.firebase_sync import (
    FirebaseContract,
    FirebaseRealtimeDatabaseClient,
)
from aria.timebase import SGT, sgt_now

EXPECTED_PROJECT_ID = "aria-e906f"

def build_parser():
    parser = argparse.ArgumentParser(
        description="Run one synthetic Firebase write/read/delete acceptance check."
    )
    parser.add_argument(
        "--input-scope",
        required=True,
        choices=("synthetic",),
        help="live acceptance is synthetic-only",
    )
    parser.add_argument(
        "--confirm-live-project",
        required=True,
        help="must exactly match the frozen Firebase project ID",
    )
    return parser

def main(argv=None, *, client_factory=FirebaseRealtimeDatabaseClient, now=sgt_now):
    args = build_parser().parse_args(argv)
    contract = FirebaseContract()
    project_id = contract.config["firebase"]["project_id"]
    if project_id != EXPECTED_PROJECT_ID or args.confirm_live_project != project_id:
        raise SystemExit("live Firebase project confirmation does not match contract")
    timestamp = now().astimezone(SGT)
    acceptance_id = "acceptance_synthetic_" + timestamp.strftime("%Y%m%dT%H%M%S%f")
    client = client_factory(contract)
    checks = client.synthetic_acceptance_round_trip(
        acceptance_id,
        created_at=timestamp,
    )
    result = {
        "acceptance_id": "zone-a-phase12.3-live-firebase-v1",
        "database_region": contract.config["firebase"]["database_region"],
        "external_test_accessed": False,
        "generated_at_sgt": timestamp.isoformat(timespec="milliseconds"),
        "input_scope": "synthetic",
        "participant_data_used": False,
        "passed": all(checks.values()),
        "project_id": project_id,
        **checks,
    }
    print(json.dumps(result, sort_keys=True))
    return result

if __name__ == "__main__":
    main()