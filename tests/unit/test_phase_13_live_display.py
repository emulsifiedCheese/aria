from datetime import timedelta
import io
import json
from threading import Event
import pytest
from aria.acceptance import live_runtime
from aria.acceptance.live_runtime import HardwareRun, build_parser, main
from aria.acceptance.runtime import RuntimeSafetyError, WindowRuntime
from aria.acceptance.synthetic_runtime import camera_record, sensor_record
from aria.collection.preflight import PreflightConfig, PreflightReport, REQUIRED_CHECKS
from aria.dashboard.app import create_dashboard_app
from aria.dashboard.integration import LocalDashboardIntegration
from aria.timebase import sgt_now

FLAGS = ["--input-scope", "non_research", "--live-display-only", "--approved-staff-present", "--mask-alignment-confirmed", "--dji-recording-disabled"]

class Camera:
    def __init__(self, mask):
        self.messages = []
        self.failed = Event()
        self.process = self
        self.alive = False
    def start(self):
        self.alive = True
    def is_alive(self):
        return self.alive
    def poll(self):
        messages, self.messages = self.messages, []
        return iter(messages)
    def stop(self):
        self.alive = False
        return {"stopped": True, "forced": False, "ipc_dropped_records": 0}

class Socket:
    def __init__(self, *args):
        self.messages = []
        self.closed = False
    def bind(self, address):
        assert address == ("0.0.0.0", 5005)
    def setblocking(self, value):
        assert value is False
    def recvfrom(self, size):
        if not self.messages:
            raise BlockingIOError
        return self.messages.pop(0), ("127.0.0.1", 4210)
    def close(self):
        self.closed = True

def test_live_display_two_tracks_without_cloud_or_files_then_pause(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    now = [sgt_now()]
    core = WindowRuntime(now=now[0])
    hardware = HardwareRun(core, None, PreflightConfig("non_research_dry_run"), None,camera_factory=Camera, socket_factory=Socket,clock=lambda: now[0], live_display_only=True)
    hardware.start(None)
    camera, sock = hardware.camera, hardware.udp
    now[0] = core.next_window + timedelta(seconds=1.75)
    for node in ("ESP-A1", "ESP-A2"):
        sock.messages.append(json.dumps(sensor_record(now[0], node)["payload"]).encode())
    camera.messages.append({"records": [camera_record(now[0], track) for track in (1, 2)], "capture_fps": 30., "processing_fps": 7.})
    hardware.poll()
    now[0] = core.next_window + timedelta(seconds=3)
    hardware.poll()
    predictions = core.integration.snapshot(now[0])["predictions"]
    assert len(predictions) == 2 and all(p["prediction_available"] for p in predictions)
    assert core.state == "running"
    assert core.integration.firebase_sync is None and core.integration.orchestrator.writer is None
    summary = hardware.summary()
    assert summary["cloud"] is False and summary["recording"] is False
    assert "predicted_activity" not in json.dumps(summary)
    hardware.pause()
    assert core.integration.snapshot(now[0])["predictions"] == []
    assert core.buffered_records == 0 and sock.closed and not camera.alive
    assert list(tmp_path.iterdir()) == []

@pytest.mark.parametrize("boundary", ["cloud", "evidence", "callback", "writer"])
def test_display_boundary_rejects_recording_and_cloud(boundary):
    core = WindowRuntime()
    cloud = evidence = None
    if boundary == "cloud":
        cloud = object()
    elif boundary == "evidence":
        evidence = object()
    elif boundary == "callback":
        core.integration.firebase_sync = object()
    else:
        core.integration.orchestrator.writer = object()
    with pytest.raises(RuntimeSafetyError, match="no_recording_or_cloud"):
        HardwareRun(core, cloud, PreflightConfig("non_research_dry_run"), evidence, live_display_only=True)

@pytest.mark.parametrize("remove,add", [
    ("--approved-staff-present", []),
    ("--mask-alignment-confirmed", []),
    ("--dji-recording-disabled", []),
    (None, ["--equipment-only"]),
    (None, ["--confirm-empty-retained-region"]),
])
def test_display_cli_requires_exclusive_confirmed_scope(remove, add, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    with pytest.raises(SystemExit):
        main([flag for flag in FLAGS if flag != remove] + add)

def test_display_cli_dispatch_and_interactive_requirement(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(live_runtime, "run_hardware", lambda args: 9 if args.live_display_only else 1)
    assert main(FLAGS) == 9
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit):
        main(FLAGS)

def test_display_dashboard_responses_disable_caching():
    app = create_dashboard_app(LocalDashboardIntegration().aggregator)
    live_runtime.disable_dashboard_caching(app)
    for path in ("/", "/_dash-layout"):
        response = app.server.test_client().get(path)
        assert response.status_code == 200
        assert "no-store" in response.headers["Cache-Control"]

def test_display_start_stop_never_constructs_evidence_or_outbox(monkeypatch, tmp_path, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("persistent boundary constructed")
    monkeypatch.setattr(live_runtime, "SandboxFirebase", forbidden)
    monkeypatch.setattr(live_runtime, "RunEvidence", forbidden)
    monkeypatch.setattr(live_runtime, "run_preflight", lambda config: PreflightReport(
        sgt_now().isoformat(), {name: True for name in REQUIRED_CHECKS}))
    created = []
    def hardware_factory(*args, **kwargs):
        hardware = HardwareRun(*args, **kwargs, camera_factory=Camera, socket_factory=Socket)
        created.append(hardware)
        return hardware
    monkeypatch.setattr(live_runtime, "HardwareRun", hardware_factory)
    class Server:
        def serve_forever(self):
            pass
        def shutdown(self):
            pass
        def server_close(self):
            pass
    def make_server(host, port, app, **kwargs):
        assert host == "127.0.0.1" and port == 8050
        return Server()
    monkeypatch.setattr("werkzeug.serving.make_server", make_server)
    monkeypatch.setattr("sys.stdin", io.StringIO("cloud-online\nstatus\nstop\n"))
    monkeypatch.setattr(live_runtime.select, "select", lambda readers, *args: (readers, [], []))
    assert live_runtime.run_hardware(build_parser().parse_args(FLAGS), output_root=tmp_path) == 0
    assert created[0].runtime.state == "stopped"
    assert created[0].camera is None and created[0].udp is None
    assert list(tmp_path.iterdir()) == []
    output = capsys.readouterr().out
    assert "Cloud is disabled" in output and '"recording": false' in output