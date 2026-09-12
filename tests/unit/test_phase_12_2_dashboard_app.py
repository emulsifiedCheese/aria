from datetime import datetime, timedelta
import json
import pytest
from dash import dcc
from aria.dashboard.app import (
    WARNING_TEXT,
    create_dashboard_app,
    render_dashboard_error,
    render_dashboard_state,
)
from aria.dashboard.state import DashboardStateAggregator, DashboardStateError
from aria.timebase import SGT
from scripts.run_local_dashboard import main, run_dashboard, seed_safe_preview

NOW = datetime(2026, 8, 24, 16, 0, 0, tzinfo=SGT)

def _walk(value):
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)
        return
    yield value
    children = getattr(value, "children", None)
    if children is not None:
        yield from _walk(children)

def _text(value):
    return " ".join(
        item
        for item in _walk(value)
        if isinstance(item, str)
    )

def _ready_aggregator():
    aggregator = DashboardStateAggregator()
    seed_safe_preview(aggregator, now=NOW)
    return aggregator

def test_ready_interface_shows_frozen_summary_without_identifiers_or_media():
    state = _ready_aggregator().snapshot(NOW)
    components = render_dashboard_state(state)
    text = _text(components)
    component_names = {type(item).__name__ for item in _walk(components)}

    assert state["overall_status"] == "ready"
    assert "Local track 1" in text
    assert "Serving/Processing" in text
    assert "0.720" in text
    assert "Camera A" in text
    assert "ESP-A1" in text and "ESP-A2" in text
    assert "Local only" in text and "Disabled" in text
    assert "synthetic1202" not in text
    assert "model_version" not in text
    assert "participant" not in text.lower()
    assert "Video" not in component_names
    assert "Img" not in component_names

def test_unavailable_stale_and_mask_blocked_states_are_explicit():
    aggregator = _ready_aggregator()
    stale = aggregator.snapshot(NOW + timedelta(seconds=6))
    stale_text = _text(render_dashboard_state(stale))
    assert "Stale — not current" in stale_text
    assert "The last result is retained only for health diagnosis." in stale_text
    assert "0.720" not in stale_text

    aggregator.set_mask_verified(False)
    blocked = aggregator.snapshot(NOW)
    blocked_text = _text(render_dashboard_state(blocked))
    assert "BLOCKED" in blocked_text
    assert "MASK_UNVERIFIED" in blocked_text
    assert WARNING_TEXT["mask_unverified"] in blocked_text

def test_render_error_fails_closed_without_exception_or_producer_text():
    error_text = _text(render_dashboard_error())
    assert "DASHBOARD STATE UNAVAILABLE" in error_text
    assert "Activity and health are hidden." in error_text
    assert "secret producer payload" not in error_text

def test_dash_layout_refresh_and_routes_remain_local_summary_only():
    app = create_dashboard_app(_ready_aggregator())
    intervals = [item for item in _walk(app.layout) if isinstance(item, dcc.Interval)]
    assert len(intervals) == 1
    assert intervals[0].interval == 1000

    client = app.server.test_client()
    assert client.get("/").status_code == 200
    response = client.get("/_dash-layout")
    assert response.status_code == 200
    layout = response.get_json()
    serialized = json.dumps(layout)
    assert "session_id" not in serialized
    assert "participant" not in serialized.lower()
    assert '"type": "Video"' not in serialized
    assert '"type": "Img"' not in serialized

    routes = {rule.rule for rule in app.server.url_map.iter_rules()}
    assert not any("video" in route.lower() or "media" in route.lower() for route in routes)

def test_callback_fails_closed_when_snapshot_validation_fails(monkeypatch):
    aggregator = _ready_aggregator()
    app = create_dashboard_app(aggregator)

    def invalid_snapshot():
        raise DashboardStateError("secret producer payload")

    monkeypatch.setattr(aggregator, "snapshot", invalid_snapshot)
    text = _text(app.aria_refresh_callback(1))
    assert "DASHBOARD STATE UNAVAILABLE" in text
    assert "secret producer payload" not in text

def test_runner_requires_safe_demo_scope_and_seeds_only_in_memory():
    with pytest.raises(SystemExit):
        main(["--demo"], run=False)
    with pytest.raises(SystemExit):
        main(["--input-scope", "synthetic"], run=False)
    with pytest.raises(SystemExit):
        main(["--demo-state", "blocked"], run=False)

    app = main(["--demo", "--input-scope", "synthetic"], run=False)
    state = app.aria_aggregator.snapshot()
    assert state["predictions"][0]["local_track_id"] == 1
    assert "session_id" not in state["predictions"][0]

    degraded = main(
        [
            "--demo",
            "--input-scope",
            "synthetic",
            "--demo-state",
            "degraded",
        ],
        run=False,
    ).aria_aggregator.snapshot()
    assert degraded["overall_status"] == "degraded"
    assert degraded["camera"]["available"] is False

    blocked = main(
        [
            "--demo",
            "--input-scope",
            "synthetic",
            "--demo-state",
            "blocked",
        ],
        run=False,
    ).aria_aggregator.snapshot()
    assert blocked["overall_status"] == "blocked"

def test_runner_uses_only_frozen_host_port_and_debug(monkeypatch):
    app = create_dashboard_app(_ready_aggregator())
    received = {}

    def fake_run(**kwargs):
        received.update(kwargs)

    monkeypatch.setattr(app, "run", fake_run)
    run_dashboard(app)
    assert received == {"host": "127.0.0.1", "port": 8050, "debug": False}