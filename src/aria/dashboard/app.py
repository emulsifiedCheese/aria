"""local dash interface for privacy-aware Zone A activity and health state"""
from __future__ import annotations
from pathlib import Path
from dash import Dash, Input, Output, dcc, html
from aria.dashboard.state import DashboardStateAggregator, DashboardStateError

WARNING_TEXT = {
    "mask_unverified": "Privacy mask is not verified. Dashboard readiness is blocked.",
    "camera_unavailable": "Camera A is unavailable.",
    "camera_stale": "Camera A has not supplied a recent processed frame.",
    "esp_a1_unavailable": "ESP-A1 has not supplied telemetry.",
    "esp_a1_stale": "ESP-A1 telemetry is stale.",
    "esp_a1_packet_loss": "ESP-A1 packet loss is above the frozen warning threshold.",
    "esp_a2_unavailable": "ESP-A2 has not supplied telemetry.",
    "esp_a2_stale": "ESP-A2 telemetry is stale.",
    "esp_a2_packet_loss": "ESP-A2 packet loss is above the frozen warning threshold.",
    "pose_unavailable": "Pose features are unavailable for at least one current track.",
    "prediction_unavailable": "A current activity prediction is unavailable.",
    "prediction_stale": "A displayed prediction is stale and is not current activity.",
    "model_error": "The local inference model could not produce a prediction.",
}

UNAVAILABLE_TEXT = {
    "excluded_interval": "Excluded interval",
    "insufficient_modalities": "Insufficient modalities",
    "missing_camera_track": "No Camera A track",
    "low_confidence": "Unavailable under the frozen prediction policy",
    "model_error": "Local model error",
}

def _value(value, *, suffix="", decimals=1):
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{decimals}f}{suffix}"
    return f"{value}{suffix}"

def _metric(label, value, *, tone=None):
    class_name = "metric"
    if tone:
        class_name += f" metric--{tone}"
    return html.Div(
        [html.Span(label, className="metric__label"), html.Strong(value)],
        className=class_name,
    )

def _component_status(available, fresh):
    if not available:
        return "Unavailable", "warning"
    if not fresh:
        return "Stale", "warning"
    return "Fresh", "ready"

def _status_header(state):
    status = state["overall_status"]
    copy = {
        "ready": "All required local inputs are fresh and the privacy mask is verified.",
        "degraded": "One or more inputs are unavailable, stale or outside the health threshold.",
        "blocked": "Privacy readiness is blocked. Do not rely on operational activity state.",
    }[status]
    return html.Section(
        [
            html.Div(
                [
                    html.Span("Overall status", className="eyebrow"),
                    html.H2(status.upper()),
                ]
            ),
            html.P(copy),
        ],
        className=f"status-banner status-banner--{status}",
        **{"aria-live": "polite"},
    )

def _prediction_card(prediction):
    available = prediction["prediction_available"] and not prediction["stale"]
    track_id = prediction["local_track_id"]
    track_label = f"Local track {track_id}" if track_id is not None else "No active track"
    if prediction["stale"]:
        activity = "Stale — not current"
        reason = "The last result is retained only for health diagnosis."
        tone = "warning"
    elif not prediction["prediction_available"]:
        activity = "Unavailable"
        reason = UNAVAILABLE_TEXT.get(prediction["unavailable_reason"], "Prediction unavailable")
        tone = "warning"
    else:
        activity = prediction["predicted_activity"]
        reason = "Current two-second window"
        tone = "ready"

    availability = prediction["availability"]
    pills = []
    for label, key in (
        ("Camera", "camera_available"),
        ("Pose", "pose_available"),
        ("ESP-A1", "esp_a1_available"),
        ("ESP-A2", "esp_a2_available"),
    ):
        is_available = availability[key]
        pills.append(
            html.Span(
                f"{label} {'available' if is_available else 'unavailable'}",
                className=f"availability-pill availability-pill--{'on' if is_available else 'off'}",
            )
        )

    confidence = (
        f"{prediction['confidence']:.3f}"
        if available and prediction["confidence"] is not None
        else "—"
    )
    return html.Article(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(track_label, className="eyebrow"),
                            html.H3(activity),
                            html.P(reason, className="muted"),
                        ]
                    ),
                    html.Div(
                        [
                            html.Span("Model confidence", className="metric__label"),
                            html.Strong(confidence, className="confidence-value"),
                        ],
                        className="confidence",
                    ),
                ],
                className="prediction-card__header",
            ),
            html.Div(pills, className="availability-row"),
            html.Div(
                [
                    _metric("Window", prediction["window_id"]),
                    _metric("Age", _value(prediction["age_seconds"], suffix=" s")),
                ],
                className="prediction-card__meta",
            ),
        ],
        className=f"prediction-card prediction-card--{tone}",
    )

def _prediction_section(predictions):
    cards = [_prediction_card(prediction) for prediction in predictions]
    if not cards:
        cards = [
            html.Article(
                [
                    html.Span("Activity state", className="eyebrow"),
                    html.H3("Waiting for a completed inference window"),
                    html.P(
                        "No earlier activity is reused while the current prediction is unavailable.",
                        className="muted",
                    ),
                ],
                className="prediction-card prediction-card--warning",
            )
        ]
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Inference", className="eyebrow"),
                            html.H2("Current activity"),
                        ]
                    ),
                    html.Span("2 s windows · local tracks", className="section-note"),
                ],
                className="section-heading",
            ),
            html.Div(cards, className="prediction-grid"),
        ],
        className="panel",
    )


def _camera_card(camera):
    status, tone = _component_status(camera["available"], camera["fresh"])
    return html.Article(
        [
            html.Div(
                [
                    html.Div([html.Span("Vision", className="eyebrow"), html.H3("Camera A")]),
                    html.Span(status, className=f"health-badge health-badge--{tone}"),
                ],
                className="health-card__header",
            ),
            html.Div(
                [
                    _metric("Capture FPS", _value(camera["capture_fps"])),
                    _metric("Processing FPS", _value(camera["processing_fps"])),
                    _metric("Frame age", _value(camera["age_seconds"], suffix=" s")),
                    _metric("Mask", "Verified" if camera["mask_verified"] else "Unverified", tone="ready" if camera["mask_verified"] else "critical"),
                ],
                className="metric-grid",
            ),
        ],
        className="health-card",
    )

def _sensor_card(node_id, sensor):
    status, tone = _component_status(sensor["available"], sensor["fresh"])
    return html.Article(
        [
            html.Div(
                [
                    html.Div([html.Span("Telemetry", className="eyebrow"), html.H3(node_id)]),
                    html.Span(status, className=f"health-badge health-badge--{tone}"),
                ],
                className="health-card__header",
            ),
            html.Div(
                [
                    _metric("Last packet", _value(sensor["age_seconds"], suffix=" s")),
                    _metric("Received", _value(sensor["packets_received"], decimals=0)),
                    _metric("Gap events", _value(sensor["packet_gap_events"], decimals=0)),
                    _metric("Estimated lost", _value(sensor["estimated_packets_lost"], decimals=0)),
                    _metric("Packet loss", _value(sensor["packet_loss_percent"], suffix=" %", decimals=2)),
                ],
                className="metric-grid",
            ),
        ],
        className="health-card",
    )

def _privacy_card(privacy):
    ready = privacy["privacy_ready"]
    return html.Article(
        [
            html.Div(
                [
                    html.Div([html.Span("Boundary", className="eyebrow"), html.H3("Privacy")]),
                    html.Span(
                        "Ready" if ready else "Blocked",
                        className=f"health-badge health-badge--{'ready' if ready else 'critical'}",
                    ),
                ],
                className="health-card__header",
            ),
            html.Div(
                [
                    _metric("Network", "Local only"),
                    _metric("Video", "Disabled"),
                    _metric("Mask", "Verified" if privacy["mask_verified"] else "Unverified"),
                ],
                className="metric-grid",
            ),
        ],
        className="health-card",
    )

def _health_section(state):
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [html.Span("Live components", className="eyebrow"), html.H2("Pipeline health")]
                    ),
                    html.Span("Freshness and runtime counters", className="section-note"),
                ],
                className="section-heading",
            ),
            html.Div(
                [
                    _camera_card(state["camera"]),
                    _sensor_card("ESP-A1", state["sensors"]["ESP-A1"]),
                    _sensor_card("ESP-A2", state["sensors"]["ESP-A2"]),
                    _privacy_card(state["privacy"]),
                ],
                className="health-grid",
            ),
        ],
        className="panel",
    )

def _warning_section(warnings):
    if not warnings:
        body = html.P("No active warnings.", className="empty-state")
    else:
        body = html.Ul(
            [
                html.Li(
                    [
                        html.Span(
                            warning["severity"].upper(),
                            className=(
                                "warning-severity "
                                f"warning-severity--{warning['severity']}"
                            ),
                        ),
                        html.Span(
                            warning["code"].upper(), className="warning-code"
                        ),
                        html.Span(WARNING_TEXT[warning["code"]]),
                    ]
                )
                for warning in warnings
            ],
            className="warning-list",
        )
    return html.Section(
        [html.Span("Attention", className="eyebrow"), html.H2("Warnings"), body],
        className="panel warning-panel",
        **{"aria-live": "polite"},
    )

def render_dashboard_state(state):
    """return product-specific components from 1 schema-valid safe snapshot"""
    return [
        _status_header(state),
        _prediction_section(state["predictions"]),
        _health_section(state),
        _warning_section(state["warnings"]),
        html.Footer(
            [
                html.Span(f"Updated {state['generated_at_sgt']}"),
                html.Span(f"Snapshot {state['snapshot_id']}"),
            ],
            className="dashboard-footer",
        ),
    ]

def render_dashboard_error():
    """fail closed without exposing exception text or producer data"""
    return [
        html.Section(
            [
                html.Span("SYSTEM STATUS", className="eyebrow"),
                html.H2("DASHBOARD STATE UNAVAILABLE"),
                html.P("The local state could not be validated. Activity and health are hidden."),
            ],
            className="status-banner status-banner--blocked",
            **{"aria-live": "assertive"},
        )
    ]

def create_dashboard_app(aggregator=None):
    aggregator = aggregator or DashboardStateAggregator()
    assets = Path(__file__).with_name("assets")
    app = Dash(
        __name__,
        assets_folder=str(assets),
        title="ARIA Zone A · Local Activity Console",
        update_title=None,
    )
    try:
        initial_content = render_dashboard_state(aggregator.snapshot())
    except DashboardStateError:
        initial_content = render_dashboard_error()

    app.layout = html.Div(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.Span("ARIA / ZONE A", className="brand-mark"),
                            html.H1("Activity monitor"),
                            html.P(
                                "Local inference and component health",
                                className="header-subtitle",
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Span("127.0.0.1", className="local-badge"),
                            html.Span("VIDEO OFF", className="local-badge local-badge--quiet"),
                        ],
                        className="header-badges",
                    ),
                ],
                className="dashboard-header",
            ),
            dcc.Interval(
                id="dashboard-refresh",
                interval=aggregator.config["server"]["refresh_interval_ms"],
                n_intervals=0,
            ),
            html.Main(id="dashboard-content", children=initial_content),
        ],
        className="dashboard-shell",
    )

    @app.callback(
        Output("dashboard-content", "children"),
        Input("dashboard-refresh", "n_intervals"),
    )
    def refresh_dashboard(_):
        try:
            return render_dashboard_state(aggregator.snapshot())
        except DashboardStateError:
            return render_dashboard_error()

    app.aria_aggregator = aggregator
    app.aria_refresh_callback = refresh_dashboard
    return app
