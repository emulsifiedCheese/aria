"""opt-in, bounded stability diagnostics; never persist input/prediction records"""
from __future__ import annotations
import math
from pathlib import Path
import time
from .aggregate_report import AggregateRunReport
from .runtime import NODES

def finite(value, *, positive=False):
    return (type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))

def storage_bytes(root, excluded):
    """stat regular output files only; do not read contents or retain filenames"""
    total = 0
    for path in Path(root).rglob('*'):
        if path.is_symlink() or path.is_relative_to(excluded):
            continue
        if path.is_file():
            total += path.stat().st_size
    return total

class StabilityRunReport(AggregateRunReport):
    """1 JSON report, checkpointed incomplete; acceptance always needs review"""

    def __init__(self, *, storage_root, clock=time.monotonic, **kwargs):
        super().__init__(**kwargs)
        self.clock = clock
        self.storage_root = Path(storage_root)
        self.created = self.last_checkpoint = clock()
        self.began = self.last_observed = self.segment_start = None
        self.longest_segment = 0.
        self.pauses = self.samples = self.stale_prediction_samples = 0
        self.max_poll_gap = self.longest_degraded = 0.
        self.degraded_start = None
        self.health_counts = dict.fromkeys(('ready', 'degraded', 'blocked', 'camera_not_fresh', 'a1_not_fresh', 'a2_not_fresh'), 0)
        self.frame_intervals = self.bad_fps = self.bad_latency = 0
        self.frame_seconds = self.capture_steps = 0.
        self.latencies = []
        self.nodes = {node: {'received': 0, 'lost': 0, 'restarts': 0, 'non_increasing': 0} for node in NODES}
        self.previous_packets = {}
        self.storage_before = self.storage_after = None
        self.storage_failed = False
        self.target_seconds = 5400
        self.value['kind'] = 'phase13_stability_aggregate_report'
        self.value['stability'] = self.snapshot()
        self._save()

    @property
    def measuring(self):
        return self.began is not None and self.segment_start is not None

    def _storage(self):
        try:
            return storage_bytes(self.storage_root, self.path.parent)
        except OSError:
            self.storage_failed = True
            return None

    def observe(self, state):
        now = self.clock()
        camera, sensors = state['camera'], state['sensors']
        ready_inputs = (camera.get('fresh') is True and camera.get('mask_verified') is True and all(sensors.get(n, {}).get('fresh') is True for n in NODES))
        if self.began is None:
            if not ready_inputs:
                return
            self.began = self.segment_start = self.last_observed = now
            self.storage_before = self._storage()
            print('Stability timer started: camera and both ESPs fresh; 90 minutes to automatic stop.', flush=True)
        if self.segment_start is None:
            #resume never erases a pause or starts a new accepted full-duration run
            self.segment_start = now
        self.max_poll_gap = max(self.max_poll_gap, now - self.last_observed)
        self.last_observed = now
        self.samples += 1
        status = state.get('overall_status')
        if status in ('ready', 'degraded', 'blocked'):
            self.health_counts[status] += 1
        else:
            self.health_counts['blocked'] += 1
        for key, fresh in (('camera_not_fresh', camera.get('fresh')), ('a1_not_fresh', sensors.get('ESP-A1', {}).get('fresh')), ('a2_not_fresh', sensors.get('ESP-A2', {}).get('fresh'))):
            self.health_counts[key] += int(fresh is not True)
        self.stale_prediction_samples += int(any(p.get('stale') is True for p in state.get('predictions', [])))
        if status != 'ready':
            if self.degraded_start is None:
                self.degraded_start = now
            self.longest_degraded = max(self.longest_degraded, now - self.degraded_start)
        else:
            if self.degraded_start is not None:
                self.longest_degraded = max(self.longest_degraded, now - self.degraded_start)
            self.degraded_start = None
        if now - self.last_checkpoint >= 60:
            self.storage_after = self._storage()
            self.value['stability'] = self.snapshot()
            self._save()  #status stays incomplete until verified shutdown
            self.last_checkpoint = now

    def pause(self):
        if self.began is None:
            return
        now = self.clock()
        if self.segment_start is not None:
            self.longest_segment = max(self.longest_segment, now - self.segment_start)
            self.segment_start = None
            self.pauses += 1
        if self.degraded_start is not None:
            self.longest_degraded = max(self.longest_degraded, now - self.degraded_start)
            self.degraded_start = None
        self.previous_packets.clear()  #do not count intentional reception gaps as UDP loss

    def packet(self, node, sequence, boot):
        if not self.measuring or node not in self.nodes:
            return
        counters = self.nodes[node]
        previous = self.previous_packets.get(node)
        if previous is not None:
            old_sequence, old_boot = previous
            if old_boot != boot:
                counters['restarts'] += 1
            elif sequence <= old_sequence:
                counters['non_increasing'] += 1
                return  #duplicate/reordered packets cannot inflate delivery
            else:
                counters['lost'] += sequence - old_sequence - 1
        counters['received'] += 1
        self.previous_packets[node] = (sequence, boot)  #transient protocol metadata only

    def frame(self, capture_fps, processing_fps):
        if not self.measuring:
            return
        if not finite(capture_fps, positive=True) or not finite(processing_fps, positive=True):
            self.bad_fps += 1
            return
        interval = 1 / processing_fps
        steps = capture_fps * interval
        if (not finite(interval, positive=True) or not finite(steps, positive=True)
                or not finite(self.frame_seconds + interval, positive=True)
                or not finite(self.capture_steps + steps, positive=True)):
            self.bad_fps += 1
            return
        self.frame_intervals += 1
        self.frame_seconds += interval
        self.capture_steps += steps

    def latency(self, milliseconds):
        if not self.measuring:
            return
        if not finite(milliseconds) or len(self.latencies) >= 4096:
            self.bad_latency += 1
            return
        self.latencies.append(milliseconds)

    def due(self):
        now = self.clock()
        return (now - self.began >= self.target_seconds if self.began is not None
                else now - self.created >= 60)

    def snapshot(self):
        now = self.clock()
        elapsed = max(0., now - self.began) if self.began is not None else 0.
        longest = max(self.longest_segment, now - self.segment_start if self.segment_start is not None else 0.)
        ordered = sorted(self.latencies)
        metrics = {
            'camera_capture_fps': self.capture_steps / self.frame_seconds if self.frame_seconds else None,
            'camera_processing_fps': self.frame_intervals / self.frame_seconds if self.frame_seconds else None,
            'prediction_latency_p95_ms': ordered[math.ceil(.95 * len(ordered)) - 1] if ordered and not self.bad_latency else None,
            'storage_growth_bytes': (self.storage_after - self.storage_before
                                     if not self.storage_failed and self.storage_before is not None
                                     and self.storage_after is not None else None),
        }
        for node, key in zip(NODES, ('esp_a1_packet_delivery_percent', 'esp_a2_packet_delivery_percent')):
            c = self.nodes[node]
            denominator = c['received'] + c['lost']
            metrics[key] = 100 * c['received'] / denominator if denominator else None
        return {
            'target_duration_seconds': self.target_seconds,
            'elapsed_seconds': elapsed, 'duration_seconds': longest,
            'full_duration_observed': longest >= self.target_seconds and self.pauses == 0,
            'measurement_started': self.began is not None,
            'pause_count': self.pauses, 'health_observations': self.samples,
            'health_observation_counts': dict(self.health_counts),
            'maximum_observation_gap_seconds': self.max_poll_gap,
            'longest_degraded_observed_seconds': self.longest_degraded,
            'stale_prediction_observations': self.stale_prediction_samples,
            'frame_intervals': self.frame_intervals, 'invalid_fps_intervals': self.bad_fps,
            'latency_samples': len(self.latencies), 'invalid_or_overflow_latency_samples': self.bad_latency,
            'telemetry_counts': {node: dict(c) for node, c in self.nodes.items()},
            'metrics': metrics, 'all_metrics_recorded': all(v is not None for v in metrics.values()),
            'assessment_required': True, 'phase_13_2_complete': False,
            'no_sustained_degradation': None, 'no_unexplained_gap': None, 'no_stale_state_reuse': None,
            'definitions': {
                'duration': 'longest_running_interval_after_first_fresh_camera_and_both_nodes_excludes_shutdown',
                'fps': 'sum_capture_index_steps_or_processed_intervals_over_sum_source_intervals_received_by_parent',
                'delivery': 'unique_forward_packets_over_received_plus_sequence_gaps_between_first_and_last_received_no_cross_pause_or_boot_gap',
                'latency': 'nearest_rank_p95_local_completed_window_processing_not_end_to_end_max_4096_numeric_samples',
                'storage': 'net_regular_file_bytes_in_project_outputs_since_measurement_start_excluding_this_report_directory_not_disk_free_space',
                'health': 'poll_observations_not_continuous_monitoring_no_automatic_stability_acceptance',
            },
        }

    def end_measurement(self):
        now = self.clock()
        if self.last_observed is not None:
            self.max_poll_gap = max(self.max_poll_gap, now - self.last_observed)
        if self.degraded_start is not None:
            self.longest_degraded = max(self.longest_degraded, now - self.degraded_start)
        self.storage_after = self._storage()
        self.value['stability'] = self.snapshot()
        self.value['stability']['measurement_finalized'] = True
        self.segment_start = None

    def finish(self, **kwargs):
        if not self.value['stability'].get('measurement_finalized'):
            self.end_measurement()
        return super().finish(**kwargs)