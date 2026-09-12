import pytest
from scripts.test_cameras import DiagnosticStats, percentile

def test_percentile_interpolates_values():
    assert percentile([10.0, 20.0], 0.95) == pytest.approx(19.5)

def test_diagnostics_measure_fps_gap_drops_and_read_latency():
    stats = DiagnosticStats(reported_fps=30.0, started_at=0.0)

    stats.record_read(True, 0.0, 0.033)
    stats.record_read(True, 0.033, 0.066)
    stats.record_read(True, 0.066, 0.133)

    result = stats.result(1.0)

    assert result["measured_fps"] == 3.0
    assert result["successful_frames"] == 3
    assert result["read_failures"] == 0
    assert result["estimated_dropped_frames"] == 1
    assert result["longest_frame_gap_ms"] == pytest.approx(67.0)
    assert result["read_latency_ms"]["maximum"] == pytest.approx(67.0)

def test_read_failures_are_included_in_drop_estimate():
    stats = DiagnosticStats(reported_fps=30.0, started_at=0.0)

    stats.record_read(False, 0.0, 0.01)
    stats.record_read(True, 0.01, 0.04)
    result = stats.result(1.0)
    assert result["successful_frames"] == 1
    assert result["read_failures"] == 1
    assert result["estimated_dropped_frames"] == 1