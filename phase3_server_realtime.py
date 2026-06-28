"""
PHASE 3 (real-time): SERVER + LIVE DASHBOARD
============================================
Ties the real-time pieces together:
  - session lifecycle + chunk-ingest endpoints (the audio streamer posts here)
  - WebSocket channel that pushes alerts/status to the dashboard (phase3_websocket)
  - per-session transcription + claim detection + validation (phase3_session)
  - the EXISTING history side panel + saved-report format (phase3_storage), unchanged
  - on session end: build the same batch-style report and save it to meetings/

Run:
  pip install fastapi "uvicorn[standard]" openai anthropic chromadb python-dotenv
  uvicorn phase3_server_realtime:app --host 127.0.0.1 --port 8000
Then open http://127.0.0.1:8000  (and run phase1_audio_streaming.py to feed audio).
"""

import os
import shutil

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from dotenv import load_dotenv
from openai import OpenAI

from phase3_session import LiveSession
from phase3_websocket import ConnectionManager
from phase3_integration import get_validator
from phase3_storage import get_storage

load_dotenv()

app = FastAPI(title="Meeting Truth Layer — Real-Time")
validator = get_validator()          # holds KB collection + report builder
storage = get_storage()
manager = ConnectionManager()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
sessions = {}                        # session_id -> LiveSession


# ----------------------------------------------------------------------------
# report building (reuse the batch format so history/storage are unchanged)
# ----------------------------------------------------------------------------
def alerts_to_validations(alerts):
    """Map live alert objects (§7.1) back to the batch validation shape that
    MeetingValidator._generate_report and storage expect."""
    out = []
    for a in alerts:
        out.append({
            "claim": a.get("claim_text", ""),
            "category": a.get("category", "UNVERIFIED"),
            "confidence": a.get("confidence_score", 0.5),
            "reasoning": a.get("reasoning", ""),
            "pm_action_suggested": a.get("suggested_response", ""),
            "priority": a.get("priority", "LOW"),
            "supporting_sources": [e.get("source") for e in a.get("evidence", [])],
            "conflicting_sources": [],
        })
    return out


def build_and_save(session):
    validations = alerts_to_validations(session.alerts)
    report = validator._generate_report(validations, session.rolling_transcript)
    result = storage.save_meeting(session.rolling_transcript, report)
    return os.path.basename(result["folder"])


# ----------------------------------------------------------------------------
# session lifecycle + ingest
# ----------------------------------------------------------------------------
@app.post("/api/session/start")
async def session_start():
    s = LiveSession(kb_collection=validator.kb_collection, openai_client=openai_client,
                    recovery_dir=str(storage.base_dir))
    sessions[s.id] = s
    return {"session_id": s.id}


@app.post("/api/session/{sid}/chunk")
async def session_chunk(sid: str, request: Request):
    session = sessions.get(sid)
    if not session:
        return JSONResponse(status_code=404, content={"error": "unknown session"})
    body = await request.body()
    await manager.send_status(sid, "processing", session.claim_count)
    try:
        alerts = await run_in_threadpool(session.ingest_chunk, body)
    except Exception:
        # persistent transcription failure on this chunk — warn, keep session alive
        await manager.send_warning(sid, "Transcription hiccup — continuing")
        await manager.send_status(sid, "listening", session.claim_count)
        return JSONResponse(status_code=202, content={"status": "skipped"})
    for a in alerts:
        await manager.send_alert(sid, a)
    await manager.send_transcript(sid, session.rolling_transcript)
    await manager.send_status(sid, "listening", session.claim_count)
    return JSONResponse(status_code=202, content={"alerts": len(alerts)})


@app.post("/api/session/{sid}/end")
async def session_end(sid: str):
    session = sessions.get(sid)
    if not session:
        return JSONResponse(status_code=404, content={"error": "unknown session"})
    await run_in_threadpool(session.finalize)
    folder = await run_in_threadpool(build_and_save, session)
    await manager.send_ended(sid, folder)
    manager.clear_session(sid)
    sessions.pop(sid, None)
    return {"folder_name": folder}


@app.websocket("/ws/session/{sid}")
async def session_ws(websocket: WebSocket, sid: str):
    await manager.connect(sid, websocket)   # replays accumulated alerts
    try:
        while True:
            await websocket.receive_text()   # ignore client messages; keepalive
    except WebSocketDisconnect:
        manager.disconnect(sid, websocket)


# ----------------------------------------------------------------------------
# retained history endpoints (unchanged behavior)
# ----------------------------------------------------------------------------
@app.get("/api/meetings")
async def list_meetings():
    return storage.list_meetings()


@app.get("/api/meetings/{folder}")
async def load_meeting(folder: str):
    try:
        return storage.load_meeting(folder)
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "not found"})


@app.delete("/api/meetings/{folder}")
async def delete_meeting(folder: str):
    target = storage.base_dir / folder
    if not str(target.resolve()).startswith(str(storage.base_dir.resolve())):
        return JSONResponse(status_code=400, content={"error": "bad path"})
    if target.is_dir():
        shutil.rmtree(target)
        return {"deleted": folder}
    return JSONResponse(status_code=404, content={"error": "not found"})


@app.post("/api/validate")
async def validate_batch(request: Request):
    """Batch fallback: validate a full pasted transcript (kept from MVP)."""
    data = await request.json()
    transcript = data.get("transcript", "")
    report = await run_in_threadpool(validator.validate_meeting, transcript)
    return report


@app.get("/api/health")
async def health():
    return {"status": "ok", "active_sessions": len(sessions)}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML


# ----------------------------------------------------------------------------
# dashboard (static; JS reads ?session= and talks to the API/WS at runtime)
# ----------------------------------------------------------------------------
DASHBOARD_HTML = r”””<!DOCTYPE html>
<html lang=”en”>
<head>
<meta charset=”UTF-8”><meta name=”viewport” content=”width=device-width, initial-scale=1.0”>
<title>Meeting Truth Layer — Live</title>
<style>
  *{box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;background:#0d0d0d;color:#e0e0e0;height:100vh;display:flex;flex-direction:column;overflow:hidden}
  header{background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:10px 20px;display:flex;align-items:center;gap:12px;border-bottom:1px solid #2a2a2a;flex-shrink:0}
  header.hidden{display:none}
  header h1{font-size:16px;margin:0;flex:1}
  .status{font-size:12px;opacity:.9;background:#ffffff18;padding:3px 8px;border-radius:12px}
  button{font:inherit;border:0;border-radius:6px;padding:7px 14px;cursor:pointer}
  .btn-start{background:#28a745;color:#fff}.btn-end{background:#dc3545;color:#fff}
  .btn-secondary{background:#2a2a2a;color:#aaa;font-size:12px;padding:5px 10px}

  /* ── main layout ── */
  .app-body{display:flex;flex:1;overflow:hidden}
  .side{width:240px;background:#111;border-right:1px solid #222;overflow-y:auto;padding:10px;flex-shrink:0}
  .side.hidden{display:none}
  .side h2{font-size:11px;text-transform:uppercase;color:#555;margin:6px 4px 8px}
  .mtg{padding:9px;border:1px solid #222;border-radius:6px;margin:5px 0;cursor:pointer;font-size:12px;background:#181818}
  .mtg:hover{background:#222}.mtg .nm{font-weight:600;color:#ddd}.mtg .meta{color:#777;font-size:11px;margin-top:3px}
  .mtg .del{float:right;color:#c00;cursor:pointer;font-size:11px}

  /* ── live area: alerts + transcript side-by-side ── */
  .live-area{flex:1;display:flex;flex-direction:column;overflow:hidden}
  .live-panels{flex:1;display:flex;overflow:hidden}

  /* alerts column */
  .alerts-col{flex:1;overflow-y:auto;padding:12px 14px;display:flex;flex-direction:column;gap:8px}
  .cmd{background:#1a1a1a;color:#bbb;padding:8px 10px;border-radius:6px;font-family:monospace;font-size:11px;margin-bottom:4px;white-space:pre-wrap;border:1px solid #2a2a2a}
  .alert{background:#141414;border-radius:10px;padding:0;border:1px solid #2a2a2a;overflow:hidden;transition:all .2s}
  .alert.hidden{display:none}
  .alert-header{display:flex;align-items:center;gap:10px;padding:10px 14px;cursor:pointer}
  .alert-badge{display:flex;align-items:center;gap:5px;padding:4px 10px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:.05em;flex-shrink:0}
  .badge-icon{font-size:12px}
  .alert-claim{font-size:13px;color:#ddd;flex:1;line-height:1.4}
  .alert-chevron{color:#555;font-size:12px;transition:transform .2s;flex-shrink:0}
  .alert.open .alert-chevron{transform:rotate(180deg)}
  .alert-body{display:none;padding:0 14px 12px;font-size:12px;color:#999;border-top:1px solid #222;margin-top:0;padding-top:10px}
  .alert.open .alert-body{display:block}
  .alert-src{margin-bottom:6px}
  .alert-sug{color:#bbb;font-style:italic}
  .alert-conf{float:right;font-size:11px;color:#555;margin-top:-2px}
  .VERIFIED .alert-badge{background:#1a3a1a;color:#4caf50;border:1px solid #2d5a2d}
  .CONTRADICTED .alert-badge{background:#3a1a1a;color:#ef5350;border:1px solid #5a2d2d}
  .UNVERIFIED .alert-badge{background:#3a3010;color:#ffc107;border:1px solid #5a4a10}
  .OUTDATED .alert-badge{background:#2a2a2a;color:#888;border:1px solid #3a3a3a}
  .NEEDS_CLARIFICATION .alert-badge{background:#0d2a30;color:#17a2b8;border:1px solid #0d3a44}
  .empty{color:#444;text-align:center;margin-top:40px;font-size:13px}

  /* transcript panel */
  .transcript-panel{width:340px;background:#111;border-left:1px solid #222;display:flex;flex-direction:column;flex-shrink:0}
  .transcript-panel.hidden{display:none}
  .transcript-header{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-bottom:1px solid #222;font-size:11px;text-transform:uppercase;color:#555;letter-spacing:.08em}
  .transcript-header button{background:none;color:#555;font-size:11px;padding:2px 6px;border:1px solid #333;border-radius:4px}
  .transcript-body{flex:1;overflow-y:auto;padding:14px;font-size:13px;line-height:1.7;color:#bbb}
  .transcript-body .t-new{color:#e0e0e0}

  /* waveform + record bar */
  .bottom-bar{flex-shrink:0;height:80px;background:#0a0a0a;border-top:1px solid #1e1e1e;display:flex;align-items:center;justify-content:center;position:relative}
  #waveCanvas{position:absolute;inset:0;width:100%;height:100%;opacity:.6}
  .record-btn{position:relative;z-index:2;width:44px;height:44px;border-radius:50%;border:3px solid #ff4444;background:transparent;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all .2s}
  .record-btn.active{background:#ff4444}
  .record-btn .dot{width:16px;height:16px;border-radius:50%;background:#ff4444;transition:all .2s}
  .record-btn.active .dot{width:12px;height:12px;border-radius:3px;background:#fff}

  /* filters + stats */
  .filters-bar{display:flex;gap:6px;flex-wrap:wrap;padding:8px 14px;border-bottom:1px solid #1e1e1e;flex-shrink:0;align-items:center}
  .filter-btn{background:#1a1a1a;border:1px solid #2a2a2a;color:#888;padding:4px 10px;border-radius:20px;cursor:pointer;font-size:11px;transition:all .2s}
  .filter-btn.active{background:#3a3a6a;color:#aac;border-color:#4a4a8a}
  .stats-inline{margin-left:auto;font-size:11px;color:#555}

  /* misc */
  .toast{position:fixed;bottom:16px;right:16px;background:#1e1e1e;color:#ddd;padding:10px 14px;border-radius:6px;font-size:12px;opacity:.95;border:1px solid #333;z-index:999}
  .modal{position:fixed;inset:0;background:rgba(0,0,0,.75);display:none;align-items:center;justify-content:center;z-index:100}
  .modal .box{background:#111;border:1px solid #333;width:80%;max-width:800px;max-height:80vh;overflow:auto;border-radius:8px;padding:20px;color:#ddd}
  .toggle-fullscreen{position:fixed;bottom:90px;left:16px;background:#1e1e2e;color:#aaa;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:11px;z-index:999;border:1px solid #333}
  .toggle-fullscreen.hidden{display:none}
</style>
</head>
<body>
<header>
  <h1>📡 Geppetto — Meeting Truth Layer</h1>
  <span class=”status” id=”status”>idle</span>
  <span id=”count” style=”font-size:12px;color:#888”></span>
  <button class=”btn-start” id=”startBtn”>Start live meeting</button>
  <button class=”btn-end” id=”endBtn” style=”display:none”>End meeting</button>
  <button class=”btn-secondary” id=”togglePanelsBtn”>Hide history</button>
</header>

<div class=”app-body”>
  <!-- history sidebar -->
  <aside class=”side” id=”sidePanel”>
    <h2>Meeting history</h2>
    <div id=”history”></div>
  </aside>

  <!-- live area -->
  <div class=”live-area”>
    <!-- filter bar -->
    <div class=”filters-bar”>
      <button class=”filter-btn active” data-filter=”all”>All</button>
      <button class=”filter-btn” data-filter=”VERIFIED”>✓ Verified</button>
      <button class=”filter-btn” data-filter=”CONTRADICTED”>✗ Contradicted</button>
      <button class=”filter-btn” data-filter=”UNVERIFIED”>? Unverified</button>
      <button class=”filter-btn” data-filter=”NEEDS_CLARIFICATION”>! Clarification</button>
      <button class=”filter-btn” data-filter=”OUTDATED”>⏰ Outdated</button>
      <span class=”stats-inline” id=”statsInline”></span>
    </div>

    <!-- alerts + transcript -->
    <div class=”live-panels”>
      <!-- alerts column -->
      <div class=”alerts-col” id=”alerts”>
        <div class=”empty”>No live session. Click “Start live meeting”.</div>
      </div>

      <!-- live transcript -->
      <div class=”transcript-panel” id=”transcriptPanel”>
        <div class=”transcript-header”>
          <span>Transcript completo</span>
          <button id=”hideTranscriptBtn”>Nascondi</button>
        </div>
        <div class=”transcript-body” id=”transcriptBody”>
          <span style=”color:#444”>Transcript will appear here when the meeting starts...</span>
        </div>
      </div>
    </div>

    <!-- waveform + record button -->
    <div class=”bottom-bar” id=”bottomBar”>
      <canvas id=”waveCanvas”></canvas>
      <div class=”record-btn” id=”recordBtn” title=”Start / End meeting”>
        <div class=”dot”></div>
      </div>
    </div>

    <div id=”cmd” style=”display:none”></div>
  </div>
</div>

<div class=”modal” id=”modal”><div class=”box” id=”modalBox”></div></div>
<button class=”toggle-fullscreen hidden” id=”toggleFullscreenBtn”>Show history</button>

<script>
let sid=null, ws=null, reconnectTimer=null;
let allAlerts=[], activeFilter='all', isLive=false;
const $=id=>document.getElementById(id);
const params=new URLSearchParams(location.search);

/* ── WebSocket ── */
function wsUrl(id){const p=location.protocol==='https:'?'wss':'ws';return `${p}://${location.host}/ws/session/${id}`;}
function connectWS(id){
  sid=id; ws=new WebSocket(wsUrl(id));
  ws.onmessage=e=>handle(JSON.parse(e.data));
  ws.onclose=()=>{ if(sid){ clearTimeout(reconnectTimer); reconnectTimer=setTimeout(()=>connectWS(sid),1500);} };
}
function handle(msg){
  if(msg.type==='alert') addAlert(msg.data);
  else if(msg.type==='transcript') updateTranscript(msg.data.text);
  else if(msg.type==='status'){
    $('status').textContent=msg.data.status;
    $('count').textContent=msg.data.claim_count? msg.data.claim_count+' claims' :'';
    if(msg.data.status==='processing') animateWave();
  }
  else if(msg.type==='warning') toast(msg.data.message);
  else if(msg.type==='ended'){ toast('Saved: '+msg.data.folder_name); endedUI(); loadHistory(); }
}

/* ── transcript ── */
function updateTranscript(text){
  const el=$('transcriptBody');
  el.innerHTML='<span class=”t-new”>'+esc(text)+'</span>';
  el.scrollTop=el.scrollHeight;
}

/* ── alerts ── */
const BADGE={
  VERIFIED:    {icon:'✓', label:'Confermato'},
  CONTRADICTED:{icon:'✗', label:'Falso'},
  UNVERIFIED:  {icon:'?', label:'Non verificato'},
  OUTDATED:    {icon:'⏰',label:'Superato'},
  NEEDS_CLARIFICATION:{icon:'!',label:'Chiarimento'},
};
function addAlert(a){
  allAlerts.unshift(a);
  renderAlerts();
  updateStats();
}
function renderAlerts(){
  const box=$('alerts');
  const filtered=allAlerts.filter(a=>activeFilter==='all'||a.category===activeFilter);
  if(filtered.length===0){ box.innerHTML='<div class=”empty”>No alerts match the current filter.</div>'; return; }
  if(box.querySelector('.empty')) box.innerHTML='';
  /* rebuild only new top item to avoid losing open state */
  const existing=new Set([...box.querySelectorAll('.alert')].map(e=>e.dataset.cid));
  filtered.forEach((a,i)=>{
    const cid=a.claim_text.slice(0,60);
    if(existing.has(cid)) return;
    const b=BADGE[a.category]||{icon:'•',label:a.category};
    const ev=(a.evidence&&a.evidence[0])||{};
    const div=document.createElement('div');
    div.className='alert '+a.category;
    div.dataset.cid=cid;
    div.innerHTML=`<div class=”alert-header”>
      <span class=”alert-badge”><span class=”badge-icon”>${b.icon}</span>${b.label.toUpperCase()}</span>
      <span class=”alert-claim”>${esc(a.claim_text)}</span>
      <span class=”alert-chevron”>▾</span>
    </div>
    <div class=”alert-body”>
      <span class=”alert-conf”>${a.confidence_score?Math.round(a.confidence_score*100)+'% conf':''}</span>
      ${ev.source?`<div class=”alert-src”>📚 ${esc(ev.source)}${ev.snippet?' — '+esc(ev.snippet.slice(0,120)):''}</div>`:''}
      ${a.suggested_response?`<div class=”alert-sug”>💬 ${esc(a.suggested_response)}</div>`:''}
    </div>`;
    div.querySelector('.alert-header').onclick=()=>div.classList.toggle('open');
    box.insertBefore(div, box.firstChild);
  });
  /* hide filtered-out items */
  [...box.querySelectorAll('.alert')].forEach(el=>{
    const a=allAlerts.find(x=>x.claim_text.slice(0,60)===el.dataset.cid);
    el.classList.toggle('hidden', !a||(activeFilter!=='all'&&a.category!==activeFilter));
  });
}
function updateStats(){
  const c={VERIFIED:0,CONTRADICTED:0,UNVERIFIED:0,OUTDATED:0,NEEDS_CLARIFICATION:0};
  allAlerts.forEach(a=>{c[a.category]=(c[a.category]||0)+1});
  $('statsInline').textContent=allAlerts.length?
    `${allAlerts.length} claims · ✓${c.VERIFIED} ✗${c.CONTRADICTED} ?${c.UNVERIFIED}`:'';
}

/* ── waveform ── */
let waveAnim=null;
function animateWave(){
  const canvas=$('waveCanvas');
  const ctx=canvas.getContext('2d');
  let frame=0;
  function draw(){
    canvas.width=canvas.offsetWidth; canvas.height=canvas.offsetHeight;
    ctx.clearRect(0,0,canvas.width,canvas.height);
    const bars=60, w=canvas.width/bars, h=canvas.height;
    for(let i=0;i<bars;i++){
      const amp=Math.sin(i*0.4+frame*0.12)*0.4+0.5;
      const bh=amp*(h*0.7)+4;
      const r=i%3===0?220:80, g=i%3===1?60:80, b=i%3===2?80:80;
      ctx.fillStyle=`rgba(${r},${g},${b},0.7)`;
      ctx.beginPath();
      ctx.roundRect(i*w+1,(h-bh)/2,w-2,bh,2);
      ctx.fill();
    }
    frame++;
    waveAnim=requestAnimationFrame(draw);
  }
  if(waveAnim) cancelAnimationFrame(waveAnim);
  draw();
  setTimeout(()=>{cancelAnimationFrame(waveAnim);waveAnim=null;},800);
}

/* ── session control ── */
async function start(){
  const r=await fetch('/api/session/start',{method:'POST'});
  const j=await r.json(); sid=j.session_id;
  history.replaceState(null,'','/?session='+sid);
  const cmd='python3 phase1_audio_streaming.py --server '+location.origin+' --session '+sid;
  $('cmd').innerHTML='<div class=”cmd”>'+esc(cmd)+'</div>';
  $('cmd').style.display='block';
  $('alerts').innerHTML='<div class=”empty”>Listening… alerts will appear here.</div>';
  allAlerts=[];
  $('transcriptBody').innerHTML='<span style=”color:#555”>Waiting for audio...</span>';
  startedUI(); connectWS(sid);
}
async function stop(){ if(!sid)return; await fetch('/api/session/'+sid+'/end',{method:'POST'}); }

function startedUI(){
  isLive=true;
  $('startBtn').style.display='none'; $('endBtn').style.display='inline-block';
  $('status').textContent='listening';
  $('recordBtn').classList.add('active');
}
function endedUI(){
  isLive=false; sid=null;
  if(ws){ws.close();ws=null;}
  $('endBtn').style.display='none'; $('startBtn').style.display='inline-block';
  $('status').textContent='idle'; $('cmd').style.display='none';
  allAlerts=[]; $('recordBtn').classList.remove('active');
}

/* ── panels ── */
function toggleHistory(){
  const side=$('sidePanel'), btn=$('togglePanelsBtn'), fb=$('toggleFullscreenBtn');
  const hidden=side.classList.toggle('hidden');
  btn.textContent=hidden?'Show history':'Hide history';
  fb.classList.toggle('hidden',!hidden);
}
$('hideTranscriptBtn').onclick=()=>$('transcriptPanel').classList.toggle('hidden');

/* ── history ── */
async function loadHistory(){
  const r=await fetch('/api/meetings'); const list=await r.json();
  $('history').innerHTML=list.length?'':'<div class=”empty” style=”margin-top:10px”>No saved meetings yet.</div>';
  list.forEach(m=>{
    const d=document.createElement('div'); d.className='mtg';
    d.innerHTML=`<span class=”del”>✕</span><div class=”nm”>${esc(m.name)}</div>
      <div class=”meta”>${m.total_claims} claims · 🔴 ${m.contradicted} · ⚠ ${m.critical_issues} critical</div>`;
    d.onclick=ev=>{ if(ev.target.classList.contains('del')){del(m.name);ev.stopPropagation();} else view(m.name); };
    $('history').appendChild(d);
  });
}
async function view(name){
  const r=await fetch('/api/meetings/'+encodeURIComponent(name)); const j=await r.json();
  const s=(j.report&&j.report.summary)||{};
  $('modalBox').innerHTML=`<h2>${esc(name)}</h2>
    <p>${s.total_claims||0} claims · 🟢 ${s.verified||0} · 🔴 ${s.contradicted||0} · 🟡 ${s.unverified||0} · ⏰ ${s.outdated||0} · ❓ ${s.needs_clarification||0}</p>
    <pre style=”white-space:pre-wrap;font-size:13px;color:#bbb”>${esc((j.transcript||'').slice(0,4000))}</pre>
    <button onclick=”document.getElementById('modal').style.display='none'” style=”margin-top:12px;background:#333;color:#ddd;border:1px solid #555”>Close</button>`;
  $('modal').style.display='flex';
}
async function del(name){ if(!confirm('Delete '+name+'?'))return; await fetch('/api/meetings/'+encodeURIComponent(name),{method:'DELETE'}); loadHistory(); }

function toast(t){ const e=document.createElement('div'); e.className='toast'; e.textContent=t; document.body.appendChild(e); setTimeout(()=>e.remove(),4000); }
function esc(s){ return (s||'').replace(/[&<>”]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','”':'&quot;'}[c])); }

/* ── bindings ── */
$('startBtn').onclick=start;
$('endBtn').onclick=stop;
$('recordBtn').onclick=()=>{ if(isLive) stop(); else start(); };
$('togglePanelsBtn').onclick=toggleHistory;
$('toggleFullscreenBtn').onclick=toggleHistory;
document.querySelectorAll('.filter-btn').forEach(btn=>{
  btn.onclick=e=>{
    document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
    e.target.classList.add('active');
    activeFilter=e.target.dataset.filter;
    renderAlerts();
  };
});
$('modal').onclick=e=>{ if(e.target===$('modal')) $('modal').style.display='none'; };

loadHistory();
if(params.get('session')){ sid=params.get('session'); startedUI(); connectWS(sid); }
</script>
</body>
</html>”””


if __name__ == "__main__":
    import uvicorn
    print("Starting Meeting Truth Layer (real-time) on http://127.0.0.1:8000 …")
    uvicorn.run(app, host="127.0.0.1", port=8000)
