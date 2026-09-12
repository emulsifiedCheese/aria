import io
import json
from datetime import timedelta
import pytest
from aria.acceptance.stability_report import StabilityRunReport
from aria.acceptance.live_runtime import RUNTIME_FILES, build_parser, main
from aria.collection.preflight import REQUIRED_CHECKS

def health():
    return {'overall_status': 'ready', 'camera': {'fresh': True, 'mask_verified': True},'sensors': {n: {'fresh': True} for n in ('ESP-A1', 'ESP-A2')}, 'predictions': []}

@pytest.fixture
def setup_report(tmp_path):
    clock = [100.]
    output = tmp_path / 'outputs'
    report = StabilityRunReport(root=output, storage_root=output, clock=lambda: clock[0],preflight={n: True for n in REQUIRED_CHECKS}, clean_boot_confirmed=False, source_files=RUNTIME_FILES)
    return report, clock, output

def test_timer_waits_for_all_fresh_inputs_and_excludes_warmup(setup_report):
    r, t, _ = setup_report
    state = health()
    state['sensors']['ESP-A2']['fresh'] = False
    r.observe(state)
    assert not r.measuring
    t[0] += 20
    r.observe(health())
    t[0] += 5399
    assert not r.due()
    assert not r.snapshot()['full_duration_observed']
    t[0] += 1
    assert r.due()
    assert r.snapshot()['duration_seconds'] == 5400
    assert r.snapshot()['full_duration_observed']

def test_startup_timeout_is_not_a_measurement(setup_report):
    r, t, _ = setup_report
    t[0] += 60
    assert r.due()
    r.end_measurement()
    s = r.value['stability']
    assert not s['measurement_started'] and s['duration_seconds'] == 0
    assert not s['all_metrics_recorded'] and not s['full_duration_observed']

def test_pause_does_not_erase_history_or_add_paused_time(setup_report):
    r, t, _ = setup_report
    r.observe(health())
    t[0] += 100
    r.pause()
    t[0] += 1000
    r.observe(health())
    t[0] += 4300
    r.end_measurement()
    s = r.value['stability']
    assert s['elapsed_seconds'] == 5400 and s['duration_seconds'] == 4300
    assert s['pause_count'] == 1 and not s['full_duration_observed']

def test_six_metrics_weighted_fps_p95_delivery_and_scoped_storage(setup_report):
    r, t, output = setup_report
    before = output / 'existing.bin'
    before.write_bytes(b'123')
    r.observe(health())
    r.frame(30., 10.)
    r.frame(20., 5.)
    for number in range(1, 21):
        r.latency(float(number))
    for node in ('ESP-A1', 'ESP-A2'):
        r.packet(node, 10, 1)
        r.packet(node, 12, 1)
    before.write_bytes(b'12345')
    (output / 'extra.bin').write_bytes(b'1234')
    t[0] += 5400
    r.end_measurement()
    m = r.value['stability']['metrics']
    assert m['camera_capture_fps'] == pytest.approx(7 / .3)
    assert m['camera_processing_fps'] == pytest.approx(2 / .3)
    assert m['prediction_latency_p95_ms'] == 19
    assert m['esp_a1_packet_delivery_percent'] == pytest.approx(200 / 3)
    assert m['esp_a2_packet_delivery_percent'] == pytest.approx(200 / 3)
    assert m['storage_growth_bytes'] == 6
    assert r.value['stability']['all_metrics_recorded']

def test_duplicate_reorder_reboot_and_pause_do_not_inflate_delivery(setup_report):
    r, _, _ = setup_report
    r.observe(health())
    for seq, boot in ((10, 1), (13, 1), (13, 1), (12, 1), (1, 2), (2, 2)):
        r.packet('ESP-A1', seq, boot)
    counts = r.snapshot()['telemetry_counts']['ESP-A1']
    assert counts == {'received': 4, 'lost': 2, 'restarts': 1, 'non_increasing': 2}
    r.pause()
    r.packet('ESP-A1', 1000, 2)
    r.observe(health())
    r.packet('ESP-A1', 2000, 2)
    assert r.snapshot()['telemetry_counts']['ESP-A1']['lost'] == 2

def test_full_latency_sample_limit_is_explicit_not_silently_rolling(setup_report):
    r, _, _ = setup_report
    r.observe(health())
    for _ in range(4097):
        r.latency(1.)
    s = r.snapshot()
    assert s['latency_samples'] == 4096 and s['invalid_or_overflow_latency_samples'] == 1
    assert s['metrics']['prediction_latency_p95_ms'] is None

@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1, True, 'private-sentinel'])
def test_bad_metric_values_cannot_be_written(setup_report, value):
    r, _, _ = setup_report
    r.observe(health())
    r.frame(value, 10.)
    r.latency(value)
    r.end_measurement()
    r._save()
    encoded = r.path.read_text()
    assert 'private-sentinel' not in encoded and 'NaN' not in encoded and 'Infinity' not in encoded
    assert r.value['stability']['metrics']['camera_capture_fps'] is None
    assert r.value['stability']['metrics']['prediction_latency_p95_ms'] is None

def test_checkpoint_contains_only_fixed_aggregates_and_no_acceptance_claim(setup_report):
    r, t, _ = setup_report
    state = health()
    state['predictions'] = [{'predicted_activity': 'private-sentinel', 'local_track_id': 'private-sentinel', 'stale': True}]
    state['camera']['source_ip'] = 'private-sentinel'
    state['sensors']['ESP-A1']['sensor_reading'] = 'private-sentinel'
    state['arbitrary'] = 'private-sentinel'
    r.observe(state)
    t[0] += 61
    state['overall_status'] = 'degraded'
    r.observe(state)
    encoded = r.path.read_text()
    saved = json.loads(encoded)
    assert 'private-sentinel' not in encoded
    assert 'predicted_activity' not in encoded and 'local_track_id' not in encoded
    assert saved['status'] == 'incomplete'
    assert saved['stability']['stale_prediction_observations'] == 2
    assert saved['stability']['no_stale_state_reuse'] is None
    assert not saved['stability']['phase_13_2_complete']
    assert list(r.path.parent.iterdir()) == [r.path]

def test_health_gaps_degradation_and_missing_inputs_remain_visible(setup_report):
    r, t, _ = setup_report
    r.observe(health())
    state = health()
    state['overall_status'] = 'degraded'
    state['sensors']['ESP-A1']['fresh'] = False
    t[0] += 10
    r.observe(state)
    t[0] += 35
    r.observe(state)
    s = r.snapshot()
    assert s['maximum_observation_gap_seconds'] == 35
    assert s['longest_degraded_observed_seconds'] == 35
    assert s['health_observation_counts']['a1_not_fresh'] == 2
    assert s['no_sustained_degradation'] is None

def test_storage_errors_are_missing_metrics_not_zero(setup_report, monkeypatch):
    r, _, _ = setup_report
    def fail(*args):
        raise OSError('private-sentinel')
    monkeypatch.setattr('aria.acceptance.stability_report.storage_bytes', fail)
    r.observe(health())
    r.end_measurement()
    assert r.value['stability']['metrics']['storage_growth_bytes'] is None
    assert 'private-sentinel' not in json.dumps(r.value)

def test_shutdown_time_cannot_complete_short_run(setup_report):
    from test_phase_13_aggregate_report import summary
    r, t, _ = setup_report
    r.observe(health())
    t[0] += 5399
    r.end_measurement()
    t[0] += 20
    assert r.finish(summary=summary(), requested_clean=True, started=True, udp_closed=True, dashboard_stopped=True)
    assert r.value['stability']['duration_seconds'] == 5399
    assert not r.value['stability']['full_duration_observed']

@pytest.mark.parametrize('flags', [
    ['--input-scope', 'synthetic', '--stability-check'],
    ['--input-scope', 'non_research', '--equipment-only', '--stability-check'],
    ['--input-scope', 'non_research', '--live-display-only', '--stability-check'],
])
def test_cli_requires_opt_in_report_and_live_scope(flags):
    with pytest.raises(SystemExit):
        main(flags)

def test_stability_cli_dispatch_preserves_confirmations(monkeypatch):
    from test_phase_13_aggregate_report import FLAGS
    monkeypatch.setattr('sys.stdin.isatty', lambda: True)
    monkeypatch.setattr('aria.acceptance.live_runtime.run_hardware', lambda args: 7 if args.stability_check else 1)
    assert main(FLAGS + ['--stability-check']) == 7

def test_real_window_runtime_reports_only_numerical_latency(setup_report):
    from aria.acceptance.runtime import WindowRuntime
    from aria.acceptance.synthetic_runtime import camera_record
    from aria.timebase import sgt_now
    r, _, _ = setup_report
    r.observe(health())
    now = sgt_now()
    core = WindowRuntime(now=now)
    core.latency_observer = r.latency
    core.resume(verified=True, now=now)
    frame_time = core.next_window + timedelta(seconds=1)
    core.camera_batch([camera_record(frame_time, 1)], capture_fps=30., processing_fps=10., now=frame_time)
    core.tick(core.next_window + timedelta(seconds=3))
    assert r.snapshot()['latency_samples'] == 1
    assert r.snapshot()['metrics']['prediction_latency_p95_ms'] >= 0
    assert core.summary()['counts']['completed_windows'] == 1

@pytest.mark.parametrize('mode', ['automatic', 'stop', 'abort', 'finalize_error'])
def test_whole_stability_loop_never_opens_recording_or_cloud(monkeypatch, tmp_path, mode):
    from aria.acceptance import live_runtime, stability_report
    from aria.collection.preflight import PreflightReport
    from aria.timebase import sgt_now
    from test_phase_13_aggregate_report import FLAGS, summary
    clock = [100.]
    closed = []
    def forbidden(*args, **kwargs):
        raise AssertionError('cloud or generic evidence constructed')
    monkeypatch.setattr(live_runtime, 'SandboxFirebase', forbidden)
    monkeypatch.setattr(live_runtime, 'RunEvidence', forbidden)
    monkeypatch.setattr(live_runtime, 'run_preflight', lambda config: PreflightReport(sgt_now().isoformat(), {n: True for n in REQUIRED_CHECKS}))
    def report_factory(**kwargs):
        kwargs['storage_root'] = tmp_path
        report = StabilityRunReport(clock=lambda: clock[0], **kwargs)
        if mode == 'finalize_error':
            def fail():
                raise OSError('synthetic-private-error')
            report.end_measurement = fail
        return report
    monkeypatch.setattr(stability_report, 'StabilityRunReport', report_factory)
    class Hardware:
        def __init__(self, runtime, cloud, config, evidence, **kwargs):
            assert cloud is None and evidence is None
            assert runtime.integration.orchestrator.writer is None
            self.runtime = runtime
            self.udp = object()
            self.camera_shutdowns = summary()['camera_shutdowns']
        def start(self, mask):
            self.runtime.resume(verified=True, now=sgt_now())
        def poll(self):
            self.stability_report.observe(health())
            self.stability_report.frame(30., 10.)
            self.runtime.latency_observer(2.)
            for node in ('ESP-A1', 'ESP-A2'):
                self.stability_report.packet(node, int(clock[0]), 1)
            clock[0] += 2700
        def close(self):
            closed.append(True)
            self.udp = None
            self.runtime.stop()
        def summary(self):
            return summary()
    monkeypatch.setattr(live_runtime, 'HardwareRun', Hardware)
    class Server:
        def serve_forever(self): pass
        def shutdown(self): pass
        def server_close(self): pass
    monkeypatch.setattr('werkzeug.serving.make_server', lambda *a, **k: Server())
    command = 'abort' if mode == 'abort' else 'stop'
    monkeypatch.setattr('sys.stdin', io.StringIO(command + '\n'))
    monkeypatch.setattr(live_runtime.select, 'select', lambda readers, *a: (
        [] if mode == 'automatic' else readers, [], []))
    result = live_runtime.run_hardware(build_parser().parse_args(FLAGS + ['--stability-check']), output_root=tmp_path)
    assert result == (1 if mode in ('abort', 'finalize_error') else 0)
    assert closed == [True]
    files = list(tmp_path.rglob('*.json'))
    assert len(files) == 1
    saved = json.loads(files[0].read_text())
    assert not saved['staff_recording_enabled'] and not saved['cloud_enabled']
    assert not saved['stability']['phase_13_2_complete']
    assert saved['stability']['full_duration_observed'] is (mode == 'automatic')
    if mode == 'automatic':
        assert saved['stability']['all_metrics_recorded']
        assert saved['stability']['maximum_observation_gap_seconds'] == 2700
    assert 'synthetic-private-error' not in files[0].read_text()