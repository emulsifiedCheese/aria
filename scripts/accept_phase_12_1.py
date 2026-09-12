#!/usr/bin/env python3
"""gen synthetic Phase 12.1 local inference acceptance evidence"""
from pathlib import Path
from aria.inference.acceptance import (
    build_phase_12_1_acceptance,
    write_phase_12_1_acceptance,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "evaluation" / "phase_12_1" / "acceptance.json"

def main():
    report = build_phase_12_1_acceptance()
    digest = write_phase_12_1_acceptance(report, OUTPUT_PATH)
    print(f"Phase 12.1 local inference acceptance: {report['status'].upper()}")
    print(f"Evidence: {OUTPUT_PATH}")
    print(f"SHA-256: {digest}")
    print(
        "End-to-end durable-delivery p95: "
        f"{report['latency']['end_to_end_with_durable_local_jsonl_delivery']['p95_ms']:.3f} ms"
    )

if __name__ == "__main__":
    main()