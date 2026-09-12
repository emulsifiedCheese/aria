import json
from io import BytesIO
from types import SimpleNamespace
import numpy as np
import pytest
from aria.collection.masked_preview import (
    APP_JAVASCRIPT,
    PAGE,
    STYLES,
    MaskedTrackPreviewServer,
    _PreviewHandler,
)

class FakeHTTPServer:
    def __init__(self, address, handler):
        self.server_address = (address[0], 54321 if address[1] == 0 else address[1])
        self.handler = handler
        self.preview = None
        self.shutdown_called = False
        self.closed = False

    def serve_forever(self):
        return

    def shutdown(self):
        self.shutdown_called = True

    def server_close(self):
        self.closed = True

def test_annotation_page_uses_persistent_per_participant_cards():
    assert "id='participant-panels'" in PAGE
    assert "id='participant'" not in PAGE
    assert "class='participant-grid'" in PAGE
    assert "selectedTracks=new Map()" in APP_JAVASCRIPT
    assert "renderParticipant(state,participantId)" in APP_JAVASCRIPT
    assert "state.replacement_required?.[participantId]" in APP_JAVASCRIPT
    assert "Continue ${replacement.previous_activity}" in APP_JAVASCRIPT

def test_annotation_polling_preserves_operator_track_and_activity_drafts():
    assert "selectedActivities=new Map()" in APP_JAVASCRIPT
    assert "input.oninput=" in APP_JAVASCRIPT
    assert "selectedTracks.set(participantId,track)" in APP_JAVASCRIPT
    assert "selectedActivities.set(participantId,value)" in APP_JAVASCRIPT
    assert "replacement?.previous_activity" in APP_JAVASCRIPT
    assert "function focusedManualTrack()" in APP_JAVASCRIPT
    assert "if(!focusedParticipant)" in APP_JAVASCRIPT

def test_participant_grid_has_requested_four_and_five_person_layouts():
    assert ".participant-grid[data-count='2'],.participant-grid[data-count='4']" in STYLES
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in STYLES
    assert ".participant-grid{display:grid;grid-template-columns:repeat(3" in STYLES
    assert "panels.dataset.count=state.participants.length" in APP_JAVASCRIPT

def test_desktop_workspace_keeps_preview_left_and_cards_right():
    assert "class='workspace'" in PAGE
    assert "class='preview-pane'" in PAGE
    assert "id='annotation-tools'" in PAGE
    assert PAGE.index("id='annotation-tools'") < PAGE.index("id='annotation-panel'")
    assert "aria-label='Participant annotation cards'" in PAGE
    assert ".workspace{display:grid;" in STYLES
    assert "grid-template-columns:minmax(420px,1fr) minmax(0,1.25fr)" in STYLES
    assert ".preview-pane{position:sticky" in STYLES
    assert "max-height:calc(100vh - 120px)" in STYLES
    assert "main{width:100%;max-width:none" in STYLES
    assert ".annotation-tools{margin-top:12px;padding:16px" in STYLES
    assert "section{margin:0;padding:12px;background:#202124;max-height:calc(100vh - 32px)" in STYLES
    assert "overflow-y:auto" in STYLES
    assert "@media(max-width:1100px){.workspace{grid-template-columns:1fr}" in STYLES
    assert "byId('annotation-tools').hidden=false" in APP_JAVASCRIPT

def test_page_has_consent_gated_dynamic_participant_control():
    assert "id='add-participant-toggle'" in PAGE
    assert "id='new-participant-id'" in PAGE
    assert "id='new-participant-consent'" in PAGE
    assert "Add consenting participant" in PAGE
    assert "post('/api/participants'" in APP_JAVASCRIPT
    assert "consent_confirmed:true" in APP_JAVASCRIPT

def test_masked_preview_is_loopback_only_and_non_caching():
    with pytest.raises(ValueError, match="127.0.0.1"):
        MaskedTrackPreviewServer(host="0.0.0.0")

    preview = MaskedTrackPreviewServer(port=0, http_server_factory=FakeHTTPServer)
    preview.start()
    try:
        assert preview.url == "http://127.0.0.1:54321/"
        assert preview._httpd.preview is preview
    finally:
        preview.stop()
    assert preview._httpd.shutdown_called is True
    assert preview._httpd.closed is True

def test_masked_preview_blanks_and_blocks_frames_while_paused():
    preview = MaskedTrackPreviewServer(port=0, http_server_factory=FakeHTTPServer)
    preview.start()
    frame = np.full((40, 60, 3), 255, dtype=np.uint8)
    try:
        assert preview.publish(frame) is True
        version, displayed, stopped = preview.wait_for_frame(-1, timeout=0.1)
        assert stopped is False
        assert np.array_equal(displayed, frame)

        preview.pause()
        paused_version, paused_frame, stopped = preview.wait_for_frame(version,timeout=0.1,)
        assert paused_version > version
        assert stopped is False
        assert not np.array_equal(paused_frame, frame)
        assert preview.publish(frame) is False
        assert preview.status()["paused"] is True

        preview.resume()
        assert preview.publish(frame) is True
    finally:
        preview.stop()
    assert preview.status()["stopped"] is True

def test_masked_preview_exposes_only_current_numerical_track_ids():
    class FakeAnnotationWriter:
        def __init__(self):
            self.snapshots = []

        def status(self):
            return {
                "participants": ["P0001"],
                "activities": ["Idle/Waiting"],
                "non_usable_reasons": ["ambiguous_activity"],
                "active": {},
                "paused": False,
                "stopped": False,
                "written_record_count": 0,
                "last_notice": "ready",
            }

        def observe_track_snapshot(self, track_ids, frame_timestamp):
            self.snapshots.append((set(track_ids), frame_timestamp))

    annotation_writer = FakeAnnotationWriter()
    preview = MaskedTrackPreviewServer(
        port=0,
        annotation_writer=annotation_writer,
        http_server_factory=FakeHTTPServer,
    )
    preview.observe_record({
        "frame_number": 10,
        "frame_timestamp_sgt": "2026-08-04T15:00:00+08:00",
        "local_track_id": 3,
    })
    preview.observe_record({
        "frame_number": 10,
        "frame_timestamp_sgt": "2026-08-04T15:00:00+08:00",
        "local_track_id": 1,
    })
    assert preview.annotation_state()["visible_track_ids"] == [1, 3]
    preview.publish(np.zeros((10, 10, 3), dtype=np.uint8))
    assert annotation_writer.snapshots == [({1, 3}, "2026-08-04T15:00:00+08:00")]

    preview.observe_record({
        "frame_number": 11,
        "frame_timestamp_sgt": "2026-08-04T15:00:00.100+08:00",
        "local_track_id": None,
    })
    assert preview.annotation_state()["visible_track_ids"] == []

def test_annotation_api_requires_local_token_and_forwards_valid_transition():
    class FakeAnnotationWriter:
        def __init__(self):
            self.payload = None

        def status(self):
            return {
                "participants": ["P0001"],
                "activities": ["Idle/Waiting"],
                "non_usable_reasons": ["ambiguous_activity"],
                "active": {},
                "paused": False,
                "stopped": False,
                "written_record_count": 0,
                "last_notice": "ready",
            }

        def transition(self, **payload):
            self.payload = payload
            return {"written": None, "status": self.status()}

    writer = FakeAnnotationWriter()
    preview = MaskedTrackPreviewServer(
        port=0,
        annotation_writer=writer,
        http_server_factory=FakeHTTPServer,
    )
    payload = json.dumps({
        "participant_id": "P0001",
        "local_track_id": 3,
        "label_status": "labelled",
        "activity": "Idle/Waiting",
        "exclusion_reason": None,
    }).encode()

    def request(token):
        handler = object.__new__(_PreviewHandler)
        handler.server = SimpleNamespace(preview=preview)
        handler.path = "/api/transition"
        handler.headers = {
            "Content-Length": str(len(payload)),
            "X-ARIA-Token": token,
        }
        handler.rfile = BytesIO(payload)
        handler.wfile = BytesIO()
        statuses = []
        handler.send_response = statuses.append
        handler.send_header = lambda *args: None
        handler.end_headers = lambda: None
        handler.do_POST()
        return statuses[0]

    assert request("wrong-token") == 403
    assert request(preview.annotation_token) == 200
    assert writer.payload["participant_id"] == "P0001"
    assert writer.payload["local_track_id"] == 3

def test_annotation_api_forwards_consent_gated_participant_addition():
    class FakeAnnotationWriter:
        def __init__(self):
            self.payload = None

        def add_participant(self, participant_id, *, consent_confirmed=False):
            self.payload = {"participant_id": participant_id,"consent_confirmed": consent_confirmed,}
            return {"status": {"participants": ["P0001", participant_id]}}

    writer = FakeAnnotationWriter()
    preview = MaskedTrackPreviewServer(
        port=0,
        annotation_writer=writer,
        http_server_factory=FakeHTTPServer,
    )
    payload = json.dumps({"participant_id": "P0002","consent_confirmed": True,}).encode()
    handler = object.__new__(_PreviewHandler)
    handler.server = SimpleNamespace(preview=preview)
    handler.path = "/api/participants"
    handler.headers = {"Content-Length": str(len(payload)),"X-ARIA-Token": preview.annotation_token,}
    handler.rfile = BytesIO(payload)
    handler.wfile = BytesIO()
    statuses = []
    handler.send_response = statuses.append
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert statuses == [200]
    assert writer.payload == {
        "participant_id": "P0002",
        "consent_confirmed": True,
    }