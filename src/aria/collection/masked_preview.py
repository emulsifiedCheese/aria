"""local, non-recording masked preview for lifecycle-owned cam a sessions"""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import cv2
import numpy as np
from .live_annotation import LiveAnnotationError

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PREVIEW_PORT = 8765
BOUNDARY = b"aria-masked-frame"

"""full c&p from hmtl"""
PAGE = """<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>
<title>ARIA masked track preview</title><link rel='stylesheet' href='/style.css'>
</head><body><main><div class='workspace'><div class='preview-pane'>
<h1>ARIA masked track preview</h1>
<p>Local display only. No video or audio is retained.</p>
<img class='preview' src='/stream.mjpg' alt='Masked Camera A track preview'>
<aside id='annotation-tools' hidden><h2>Live activity annotation</h2>
<p>Each participant has independent track and activity controls. Times and
two-second window boundaries are recorded automatically.</p>
<div class='participant-add'><button id='add-participant-toggle' type='button'>
Add consenting participant</button><div id='add-participant-form' hidden>
<label>Pseudonymised participant ID
<input id='new-participant-id' type='text' inputmode='numeric' pattern='P[0-9]{4}'
placeholder='P0012' maxlength='5' autocomplete='off'></label>
<label class='consent-confirmation'><input id='new-participant-consent'
type='checkbox'> I confirm this participant has consented and acknowledged the
current approved participant information.</label><div class='buttons'>
<button id='add-participant-confirm' type='button'>Create participant card</button>
<button id='add-participant-cancel' type='button'>Cancel</button></div></div></div>
<p id='notice' role='status'></p></aside></div>
<section id='annotation-panel' aria-label='Participant annotation cards' hidden>
<div id='participant-panels' class='participant-grid'></div></section></div></main>
<script src='/app.js'></script></body></html>"""

STYLES = """*{box-sizing:border-box}body{font-family:system-ui,sans-serif;margin:0;
background:#111;color:#eee}main{width:100%;max-width:none;margin:0;padding:16px}.workspace{display:grid;
grid-template-columns:minmax(420px,1fr) minmax(0,1.25fr);gap:16px;align-items:start}
.preview-pane{position:sticky;top:16px;align-self:start}.preview{display:block;width:100%;
max-height:calc(100vh - 120px);object-fit:contain;background:#000;border:1px solid #555}
.annotation-tools{margin-top:12px;padding:16px;background:#202124}
section{margin:0;padding:12px;background:#202124;max-height:calc(100vh - 32px);
overflow-y:auto;overscroll-behavior:contain}
.participant-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.participant-grid[data-count='1']{grid-template-columns:minmax(0,1fr)}
.participant-grid[data-count='2'],.participant-grid[data-count='4']{
grid-template-columns:repeat(2,minmax(0,1fr))}
.participant-card{min-width:0;padding:14px;border:1px solid #555;border-radius:8px;
background:#161719}.participant-card h3{display:flex;justify-content:space-between;gap:8px;
align-items:center;margin-top:0}.participant-status{font-size:.8em;font-weight:500;color:#aaa}
.participant-status.active{color:#8bd3ff}.participant-status.warning{color:#ffb74d}
label,fieldset{display:grid;gap:7px}fieldset{margin:10px 0;border-color:#555}
select,input,button{box-sizing:border-box;font:inherit;padding:9px;max-width:100%}
.buttons,.track-buttons{display:flex;flex-wrap:wrap;gap:7px;margin:8px 0 12px}
.buttons button,.track-buttons button{cursor:pointer}.track.selected,.activity.selected{
outline:3px solid #55c2ff}.track.in-use{border-color:#8bd3ff}.secondary button{flex:1 1 130px}
.replacement{border-left:4px solid #ffb74d;padding:9px 11px;margin:8px 0 12px;
background:#302418}.replacement p{margin:0 0 8px}.current{min-height:2.8em;color:#bbb}
#notice{min-height:1.5em;color:#8bd3ff}.warning{color:#ffb74d}h1,h2,h3{margin-bottom:8px}
.participant-add{margin:12px 0}.participant-add>button{cursor:pointer}
#add-participant-form{max-width:620px;margin-top:10px;padding:12px;border:1px solid #555;
border-radius:8px;background:#161719}.consent-confirmation{display:flex;grid-template-columns:auto 1fr;
align-items:start;margin-top:10px}.consent-confirmation input{margin-top:3px}
@media(max-width:1100px){.workspace{grid-template-columns:1fr}.preview-pane{position:static}
.preview{max-height:none}section{max-height:none;overflow:visible}.participant-grid{
grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){main{padding:8px}.participant-grid{grid-template-columns:1fr}}
"""

APP_JAVASCRIPT = r"""const token=__TOKEN__;let latestState=null;
const selectedTracks=new Map();const selectedActivities=new Map();
const byId=id=>document.getElementById(id);
const notice=byId('notice');
const addToggle=byId('add-participant-toggle');const addForm=byId('add-participant-form');
const addInput=byId('new-participant-id');const addConsent=byId('new-participant-consent');
const addConfirm=byId('add-participant-confirm');const addCancel=byId('add-participant-cancel');
function option(value,label=value){const item=document.createElement('option');item.value=value;
item.textContent=label;return item}
async function post(path,payload){const response=await fetch(path,{method:'POST',headers:{
'Content-Type':'application/json','X-ARIA-Token':token},body:JSON.stringify(payload)});
const result=await response.json();if(!response.ok)throw new Error(result.error||'Request failed');
render(result.status||result);return result}
function resetParticipantForm(){addInput.value='';addConsent.checked=false;addForm.hidden=true}
addToggle.onclick=()=>{addForm.hidden=false;addInput.focus()};addCancel.onclick=resetParticipantForm;
addConfirm.onclick=async()=>{const participantId=addInput.value.trim().toUpperCase();
try{if(!/^P[0-9]{4}$/.test(participantId))throw new Error('Use a P0000-style participant ID.');
if(!addConsent.checked)throw new Error('Confirm participant consent before creating the card.');
await post('/api/participants',{participant_id:participantId,consent_confirmed:true});
resetParticipantForm()}catch(error){notice.textContent=error.message}};
function chooseTrack(participantId,value,card){const track=Number(value);
selectedTracks.set(participantId,track);card.querySelector('.track-input').value=track;
card.querySelectorAll('.track').forEach(button=>button.classList.toggle('selected',
Number(button.dataset.track)===track))}
function chooseActivity(participantId,value,card){selectedActivities.set(participantId,value);
card.querySelectorAll('.activity').forEach(button=>button.classList.toggle('selected',
button.dataset.activity===value))}
function base(participantId,card){const input=card.querySelector('.track-input');
if(input.value==='')throw new Error(`Select a visible track ID for ${participantId} first.`);
const value=Number(input.value);if(!Number.isInteger(value)||value<0)
throw new Error(`Select a visible track ID for ${participantId} first.`);
return {participant_id:participantId,local_track_id:value}}
async function transition(participantId,card,extra){try{await post('/api/transition',{
...base(participantId,card),...extra})}catch(error){notice.textContent=error.message}}
function replacementPanel(state,participantId,card){const replacement=
state.replacement_required?.[participantId];if(!replacement)return;
if(selectedTracks.get(participantId)===replacement.missing_local_track_id)
selectedTracks.delete(participantId);const panel=document.createElement('div');
panel.className='replacement';const text=document.createElement('p');text.textContent=
`Replacement track required: track ${replacement.missing_local_track_id} disappeared. Previous activity: ${replacement.previous_activity||'uncertain'}.`;
panel.append(text);if(replacement.previous_activity){const keep=document.createElement('button');
keep.type='button';keep.textContent=`Continue ${replacement.previous_activity}`;keep.onclick=()=>
transition(participantId,card,{label_status:'labelled',activity:replacement.previous_activity,
exclusion_reason:null});panel.append(keep)}card.append(panel)}
function renderParticipant(state,participantId){const card=document.createElement('article');
card.className='participant-card';card.dataset.participant=participantId;
const active=state.active?.[participantId];const replacement=
state.replacement_required?.[participantId];if(active&&!selectedTracks.has(participantId))
selectedTracks.set(participantId,active.local_track_id);
if(active?.label_status==='labelled'&&active.activity)
selectedActivities.set(participantId,active.activity);
else if(replacement?.previous_activity)
selectedActivities.set(participantId,replacement.previous_activity);
const heading=document.createElement('h3');const name=document.createElement('span');
name.textContent=participantId;const status=document.createElement('span');
status.className='participant-status'+(replacement?' warning':active?' active':'');
status.textContent=replacement?'Replacement required':active?'Active':'Not active';
heading.append(name,status);card.append(heading);replacementPanel(state,participantId,card);
const tracks=document.createElement('fieldset');const legend=document.createElement('legend');
legend.textContent='Visible track ID';tracks.append(legend);const trackButtons=
document.createElement('div');trackButtons.className='track-buttons';
state.visible_track_ids.forEach(value=>{const button=document.createElement('button');
button.type='button';button.className='track';button.dataset.track=value;
const assigned=Object.values(state.active||{}).find(item=>item.local_track_id===value&&
item.participant_id!==participantId);if(assigned){button.classList.add('in-use');
button.textContent=`Track ${value} (${assigned.participant_id})`}else button.textContent=`Track ${value}`;
button.onclick=()=>chooseTrack(participantId,value,card);trackButtons.append(button)});
tracks.append(trackButtons);const manual=document.createElement('label');
manual.textContent='Manual track ID';const input=document.createElement('input');
input.className='track-input';input.type='number';input.min='0';input.step='1';
const selected=selectedTracks.get(participantId);if(selected!==undefined)input.value=selected;
input.oninput=()=>{if(input.value==='')selectedTracks.delete(participantId);
else{const value=Number(input.value);if(Number.isInteger(value)&&value>=0)
chooseTrack(participantId,value,card)}};manual.append(input);tracks.append(manual);
card.append(tracks);if(selected!==undefined)chooseTrack(participantId,selected,card);
const activityTitle=document.createElement('strong');activityTitle.textContent='Activity';
card.append(activityTitle);const activities=document.createElement('div');
activities.className='buttons';state.activities.forEach(activity=>{const button=
document.createElement('button');button.type='button';button.className='activity';
button.dataset.activity=activity;button.textContent=activity;
if(selectedActivities.get(participantId)===activity)button.classList.add('selected');
button.onclick=()=>{chooseActivity(participantId,activity,card);transition(participantId,card,{
label_status:'labelled',activity,exclusion_reason:null})};activities.append(button)});
card.append(activities);const reasonLabel=document.createElement('label');
reasonLabel.textContent='Uncertainty/exclusion reason';const reason=document.createElement('select');
reason.className='reason';state.non_usable_reasons.forEach(value=>
reason.append(option(value,value.replace(/_/g,' '))));reasonLabel.append(reason);card.append(reasonLabel);
const secondary=document.createElement('div');secondary.className='buttons secondary';
const uncertain=document.createElement('button');uncertain.type='button';
uncertain.textContent='Mark uncertain';uncertain.onclick=()=>transition(participantId,card,{
label_status:'uncertain',activity:null,exclusion_reason:reason.value});
const excluded=document.createElement('button');excluded.type='button';
excluded.textContent='Mark excluded';excluded.onclick=()=>transition(participantId,card,{
label_status:'excluded',activity:null,exclusion_reason:reason.value});
const end=document.createElement('button');end.type='button';end.textContent='End annotation';
end.onclick=async()=>{try{selectedActivities.delete(participantId);
await post('/api/stop',{participant_id:participantId})}
catch(error){notice.textContent=error.message}};secondary.append(uncertain,excluded,end);
card.append(secondary);const current=document.createElement('p');current.className='current';
current.textContent=active?`Track ${active.local_track_id} — ${active.activity||active.label_status} — since ${active.interval_start_sgt}`:
replacement?'Select the participant\'s current track to continue.':'No annotation active.';
card.append(current);return card}
function focusedManualTrack(){const control=document.activeElement;
if(!control?.classList?.contains('track-input'))return null;
const card=control.closest('.participant-card');if(!card)return null;
return card.dataset.participant}
function render(state){latestState=state;if(!state.annotation_enabled)return;
byId('annotation-tools').hidden=false;byId('annotation-panel').hidden=false;
notice.textContent=state.last_notice||'';
addToggle.hidden=!state.participant_add_enabled;
const panels=byId('participant-panels');panels.dataset.count=state.participants.length;
const focusedParticipant=focusedManualTrack();
if(!focusedParticipant)
panels.replaceChildren(...state.participants.map(value=>renderParticipant(state,value)));
document.querySelectorAll('button,input,select').forEach(control=>
control.disabled=state.paused||state.stopped)}
async function refresh(){try{const response=await fetch('/api/state',{cache:'no-store'});
render(await response.json())}catch(error){notice.textContent='Preview connection unavailable.'}}
refresh();setInterval(refresh,1000);"""

class _PreviewHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class _PreviewHandler(BaseHTTPRequestHandler):
    server_version = "ARIA-Masked-Preview/1"

    def log_message(self, format, *args):
        return

    def _no_store_headers(self, content_type):
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self'; script-src 'self'; "
            "style-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'",
        )

    def _send_body(self, status, content_type, body):
        self.send_response(status)
        self._no_store_headers(content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status, value):
        self._send_body(
            status,
            "application/json; charset=utf-8",
            json.dumps(value, sort_keys=True).encode("utf-8"),
        )

    def do_GET(self):
        preview = self.server.preview
        if self.path == "/":
            self._send_body(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
            return
        if self.path == "/style.css":
            self._send_body(200, "text/css; charset=utf-8", STYLES.encode("utf-8"))
            return
        if self.path == "/app.js":
            script = APP_JAVASCRIPT.replace(
                "__TOKEN__", json.dumps(preview.annotation_token)
            ).encode("utf-8")
            self._send_body(200, "text/javascript; charset=utf-8", script)
            return
        if self.path == "/api/state":
            self._send_json(200, preview.annotation_state())
            return

        if self.path != "/stream.mjpg":
            self.send_error(404)
            return

        self.send_response(200)
        self._no_store_headers("multipart/x-mixed-replace; boundary=" + BOUNDARY.decode("ascii"))
        self.end_headers()
        version = -1
        try:
            while True:
                version, frame, stopped = preview.wait_for_frame(version)
                if frame is not None:
                    success, encoded = cv2.imencode(
                        ".jpg",
                        frame,
                        [cv2.IMWRITE_JPEG_QUALITY, preview.jpeg_quality],
                    )
                    if success:
                        payload = encoded.tobytes()
                        self.wfile.write(b"--" + BOUNDARY + b"\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(
                            f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
                        )
                        self.wfile.write(payload + b"\r\n")
                        self.wfile.flush()
                if stopped:
                    break
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def do_POST(self):
        preview = self.server.preview
        if self.path not in {"/api/transition", "/api/stop", "/api/participants"}:
            self.send_error(404)
            return
        if self.headers.get("X-ARIA-Token") != preview.annotation_token:
            self._send_json(403, {"error": "Invalid local annotation token"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 2 or length > 4096:
                raise LiveAnnotationError("Invalid annotation request size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise LiveAnnotationError("Annotation request must be an object")
            if preview.annotation_writer is None:
                raise LiveAnnotationError("Annotations are not enabled for this session")
            if self.path == "/api/transition":
                result = preview.annotation_writer.transition(**payload)
            elif self.path == "/api/stop":
                if set(payload) != {"participant_id"}:
                    raise LiveAnnotationError("Stop requires only participant_id")
                result = preview.annotation_writer.stop_participant(
                    payload["participant_id"]
                )
            else:
                if set(payload) != {"participant_id", "consent_confirmed"}:
                    raise LiveAnnotationError(
                        "Participant registration requires ID and consent confirmation"
                    )
                result = preview.annotation_writer.add_participant(**payload)
        except (LiveAnnotationError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._send_json(400, {"error": str(error)})
            return
        self._send_json(200, result)

class MaskedTrackPreviewServer:

    def __init__(
        self,
        *,
        host=LOOPBACK_HOST,
        port=DEFAULT_PREVIEW_PORT,
        jpeg_quality=80,
        annotation_writer=None,
        http_server_factory=_PreviewHTTPServer,
    ):
        if host != LOOPBACK_HOST:
            raise ValueError("Masked preview must bind only to 127.0.0.1")
        if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535:
            raise ValueError("preview port must be an integer from 0 to 65535")
        if not isinstance(jpeg_quality, int) or not 1 <= jpeg_quality <= 100:
            raise ValueError("JPEG quality must be an integer from 1 to 100")
        self.host = host
        self.requested_port = port
        self.jpeg_quality = jpeg_quality
        self.http_server_factory = http_server_factory
        self.annotation_writer = annotation_writer
        self.annotation_token = secrets.token_urlsafe(24)
        self._condition = threading.Condition()
        self._frame = None
        self._frame_shape = (720, 1280, 3)
        self._version = 0
        self._paused = False
        self._stopped = False
        self._httpd = None
        self._thread = None
        self._visible_frame_number = None
        self._visible_frame_timestamp = None
        self._visible_track_ids = set()

    @property
    def port(self):
        if self._httpd is None:
            return self.requested_port
        return self._httpd.server_address[1]

    @property
    def url(self):
        return f"http://{self.host}:{self.port}/"

    def start(self):
        if self._httpd is not None:
            raise RuntimeError("Masked preview server is already started")
        self._httpd = self.http_server_factory(
            (self.host, self.requested_port),
            _PreviewHandler,
        )
        self._httpd.preview = self
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="aria-masked-preview",
            daemon=True,
        )
        self._thread.start()
        return self.url

    def _set_frame(self, frame):
        with self._condition:
            self._frame = frame.copy()
            self._frame_shape = frame.shape
            self._version += 1
            self._condition.notify_all()

    def publish(self, frame):
        if frame is None:
            raise ValueError("Masked preview frame must not be None")
        with self._condition:
            if self._paused or self._stopped:
                return False
            track_ids = set(self._visible_track_ids)
            frame_timestamp = self._visible_frame_timestamp
            self._frame = frame.copy()
            self._frame_shape = frame.shape
            self._version += 1
            self._condition.notify_all()
        if self.annotation_writer is not None and frame_timestamp is not None:
            self.annotation_writer.observe_track_snapshot(
                track_ids,
                frame_timestamp,
            )
        return True

    def observe_record(self, record):

        frame_number = record.get("frame_number")
        frame_timestamp = record.get("frame_timestamp_sgt")
        track_id = record.get("local_track_id")
        with self._condition:
            if frame_number != self._visible_frame_number:
                self._visible_frame_number = frame_number
                self._visible_frame_timestamp = frame_timestamp
                self._visible_track_ids = set()
            if isinstance(track_id, int) and not isinstance(track_id, bool):
                self._visible_track_ids.add(track_id)

    def annotation_state(self):
        if self.annotation_writer is None:
            return {
                "annotation_enabled": False,
                "visible_track_ids": [],
                "paused": self._paused,
                "stopped": self._stopped,
            }
        state = self.annotation_writer.status()
        with self._condition:
            state["visible_track_ids"] = sorted(self._visible_track_ids)
        state["annotation_enabled"] = True
        return state

    def _blank_frame(self, label):
        height, width = self._frame_shape[:2]
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.putText(
            frame,
            label,
            (max(20, width // 20), max(60, height // 2)),
            cv2.FONT_HERSHEY_SIMPLEX,
            max(0.8, width / 1600),
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return frame

    def pause(self):
        with self._condition:
            self._paused = True
            self._visible_track_ids = set()
        self._set_frame(self._blank_frame("ARIA COLLECTION PAUSED"))

    def resume(self):
        with self._condition:
            if self._stopped:
                raise RuntimeError("Stopped masked preview cannot resume")
            self._paused = False

    def wait_for_frame(self, previous_version, timeout=1.0):
        with self._condition:
            self._condition.wait_for(lambda: self._version != previous_version or self._stopped,timeout=timeout,)
            return self._version, self._frame, self._stopped

    def stop(self):
        with self._condition:
            if self._stopped:
                return
            self._paused = True
            self._visible_track_ids = set()
        self._set_frame(self._blank_frame("ARIA SESSION STOPPED"))
        with self._condition:
            self._stopped = True
            self._condition.notify_all()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def status(self):
        with self._condition:
            return {
                "url": self.url,
                "paused": self._paused,
                "stopped": self._stopped,
                "frame_available": self._frame is not None,
            }