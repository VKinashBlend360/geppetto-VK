# GEPPETTO 2: REAL-TIME DASHBOARD — UPDATED HANDOFF

**Updated:** After adding meeting history side panel to Phase 3

---

## RECENT CHANGES TO PHASE 3 (STABLE)

### New Feature: Meeting History Side Panel
✅ **Added to phase3_server.py:**
- Left sidebar showing all saved meetings
- Quick stats per meeting (claims, verified, contradicted)
- **Load button** → Opens full previous report
- **Delete button** → Removes meeting from history
- Auto-refresh on load/delete

**Files modified:**
- `phase3_server.py` — Added sidebar UI + `/api/meetings/{folder_name}` DELETE endpoint

**API endpoints (new):**
- `GET /api/meetings` — List all meetings ✅ (already existed)
- `GET /api/meetings/{folder_name}` — Load meeting ✅ (already existed)
- `DELETE /api/meetings/{folder_name}` — Delete meeting ✅ (NEW)

---

## UPDATED FILE INVENTORY FOR GEPPETTO 2

### COPY FROM GEPETO - IVAN (Unchanged)

```
✅ phase2_kb_setup.py          (KB creation)
✅ phase2_validator.py         (Validation logic)
✅ phase3_integration.py       (Orchestration)
✅ phase3_storage.py           (File storage)
✅ .env                        (API keys)
✅ chroma_data/                (Knowledge base)
```

### COPY FROM GEPETO - IVAN (Updated for Geppetto 2)

```
✅ phase3_server.py            ⚠️ NOW HAS SIDE PANEL
   - Added sidebar HTML
   - Added loadMeetings() JS function
   - Added loadMeeting(folderName) JS function
   - Added deleteMeeting(folderName) JS function
   - Added DELETE /api/meetings/{folder_name} endpoint
   
   Note: Keep this version, don't use old one!
```

### CREATE NEW (Geppetto 2 specific)

```
🆕 phase1_audio_streaming.py    (Stream audio chunks to server)
🆕 phase3_websocket.py          (WebSocket handlers for real-time)
🆕 phase3_server_realtime.py    (FastAPI with streaming endpoints)
```

---

## QUICK START FOR NEW CHAT (Updated)

**Copy this into a fresh Claude chat:**

```
Context: Building real-time meeting validation dashboard (Geppetto 2).

Previous work: Complete stable MVP built (Gepeto - Ivan).
- Phase 1: Audio capture + Whisper transcription ✅
- Phase 2: KB + 5-category claim validation ✅  
- Phase 3: Post-meeting dashboard with storage ✅
  - NEW: Meeting history side panel (load/delete past meetings)

Files to copy from Gepeto - Ivan:
  ✅ phase2_kb_setup.py, phase2_validator.py, phase3_integration.py
  ✅ phase3_storage.py, .env, chroma_data/
  ⚠️ phase3_server.py (USE THE UPDATED VERSION WITH SIDE PANEL)

Current task: Upgrade Phase 3 to show alerts during meeting (real-time).

Technical approach:
1. Audio streaming: Capture audio → Send chunks (every 2-3s) to server
2. Streaming transcription: Server sends chunks to Whisper API
3. Live validation: Extract claims + validate as transcript grows
4. WebSocket: Push alerts to dashboard in real-time
5. Dashboard: Update alerts as they arrive

NEW: Side panel already shows meeting history, so real-time feature needs to:
  - Keep side panel intact
  - Add live validation alerts during meeting
  - Update side panel with new meeting as it's being validated
  - Save final report to meetings/ folder

Files needed:
  - phase1_audio_streaming.py (new - stream audio to server)
  - phase3_websocket.py (new - WebSocket handlers)
  - phase3_server_realtime.py (new - FastAPI with streaming + side panel)

Constraint: Reduce context. Save findings to Geppetto 2 folder.

Next: Read REALTIME_ARCHITECTURE.md and REALTIME_QUICK_START.md
```

---

## KEY CHANGE: Side Panel Integration

The real-time feature needs to preserve the **meeting history side panel** while adding live alerts.

### Current Side Panel:
- Shows saved meetings from `meetings/` folder
- User can load past reports
- User can delete old meetings

### Real-Time Integration:
- As new meeting is being validated, show **live progress** in main area
- Once meeting ends, automatically add to side panel
- User can then load it anytime

**Design consideration:** 
- Real-time dashboard should show live alerts (center)
- History panel stays on left
- No conflicts between the two

---

## ARCHITECTURE UPDATE

```
BEFORE (post-meeting only):
┌─ Sidebar: History Panel
└─ Main: Paste transcript → Validate → Show results

AFTER (real-time):
┌─ Sidebar: History Panel (unchanged)
└─ Main: Live validation during meeting
           ↓ (after meeting)
           → Added to sidebar automatically
           → Can load anytime
```

---

## IMPLEMENTATION CHECKLIST (Updated)

- [ ] Copy updated phase3_server.py from Gepeto - Ivan
- [ ] Build phase1_audio_streaming.py
- [ ] Build phase3_websocket.py
- [ ] Build phase3_server_realtime.py
- [ ] Integrate side panel into real-time server
- [ ] Real-time validation pushes to both dashboard AND updates history
- [ ] Auto-add new meeting to sidebar after validation
- [ ] Test: live validation + history sidebar together
- [ ] Test: load past meeting while new one validating (no conflicts)

---

## FILE DEPENDENCIES

```
Geppetto 2 → phase3_server_realtime.py depends on:
  ├─ phase3_integration.py (orchestration)
  ├─ phase3_storage.py (save to file)
  ├─ phase2_validator.py (validation)
  ├─ phase2_kb_setup.py (KB)
  └─ chroma_data/ (knowledge base)

Plus NEW:
  ├─ phase1_audio_streaming.py (stream audio)
  └─ phase3_websocket.py (WebSocket handlers)
```

---

## NEXT STEPS

1. Create Geppetto 2 folder and select in Cowork
2. Copy files from Gepeto - Ivan (use updated phase3_server.py!)
3. Follow REALTIME_QUICK_START.md to build real-time features
4. Keep side panel - just add live alerts alongside it

---

**Key takeaway:** The side panel is now part of Phase 3, so Geppetto 2's real-time feature needs to preserve and enhance it, not replace it.

Good luck! 🚀
