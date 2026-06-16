# Meeting Truth Layer (Geppetto) — Real-Time Version

## Requirements & Architecture Handoff

**Status:** Handoff for build
**Date:** 2026-06-15
**Owner:** Ivan Fonseca
**Audience:** Engineer(s) building the real-time release ("Geppetto 2")
**Predecessor:** Stable post-meeting MVP (this repo, `phase1`–`phase3`)

---

## 1. Purpose & Background

The Meeting Truth Layer (MTL / "Geppetto") is a real-time AI fact-checking agent for project managers. It listens to a meeting, extracts factual claims, validates each claim against an approved knowledge base, and privately alerts the PM when a statement does not match documented sources (e.g., someone says "QA is complete" while the tracker shows 82%).

The **current build is post-meeting only**: the PM pastes (or loads) a finished transcript, the system validates it in one batch, and a dashboard shows the results plus a history of past meetings. This works and is stable.

The **goal of this release** is to move validation from *after* the meeting to *during* the meeting: stream audio, transcribe and validate incrementally, and push alerts to the dashboard live — without losing the existing history panel and stored reports.

This document defines what must be built, the current architecture, and the proposed real-time architecture.

---

## 2. Goals & Non-Goals

### Goals

1. Capture meeting audio continuously and transcribe it in near real time.
2. Detect and validate claims incrementally as the transcript grows.
3. Push validation alerts to the dashboard live (sub-10s from spoken claim to on-screen alert).
4. Preserve the existing meeting-history side panel and stored-report behavior.
5. Automatically persist the completed meeting to history when the session ends.
6. Keep the MVP cost profile (~$6–15/month for an active PM) and run on the user's Windows laptop with no GPU.

### Non-Goals (this release)

- Native desktop app (Electron/PyQt) — stays a local web dashboard.
- Multi-user / multi-tenant hosting, auth, or cloud deployment.
- Speaker diarization ("who said it").
- Local/offline Whisper or local LLM (documented as future, not built now).
- Knowledge-base write-back / source-correction workflow.
- Mobile or browser-extension clients.

---

## 3. Current Architecture (As-Built)

### 3.1 Overview

The current system is a **synchronous, batch pipeline**. Nothing is real-time: a complete transcript goes in, a complete report comes out.

```
                         CURRENT (post-meeting, batch)

  ┌──────────────┐    paste / load full transcript    ┌────────────────────┐
  │   Browser    │ ─────────────────────────────────► │  FastAPI server     │
  │  Dashboard   │                                     │  (phase3_server.py) │
  │  (HTML/JS)   │ ◄───────── JSON report ──────────── │                     │
  │  + history   │                                     └─────────┬──────────┘
  │  side panel  │                                               │
  └──────────────┘                                               │ validate_meeting()
        ▲                                                         ▼
        │ GET/DELETE history                          ┌────────────────────────┐
        │                                             │ MeetingValidator        │
        │                                             │ (phase3_integration.py)  │
        │                                             └───────┬─────────┬───────┘
        │                                                     │         │
        │                                          claims     ▼         ▼  retrieve
   ┌────┴───────────┐                          ┌──────────────────┐  ┌──────────────┐
   │ meetings/ disk │ ◄── save report ──────── │ Validator        │  │ ChromaDB     │
   │ (JSON + HTML)  │   (phase3_storage.py)    │ (phase2)         │  │ chroma_data/ │
   └────────────────┘                          │ Claude Haiku     │  │ + embeddings │
                                                └──────────────────┘  └──────────────┘

  Audio path (separate, offline tool — not wired into the server):
  Meeting audio ──► VB-Cable ──► PyAudio ──► record .wav ──► Whisper API ──► transcript.txt
  (phase1_audio_pipeline.py)
```

### 3.2 Components (as built in this repo)

| Layer | Implementation | File(s) | Notes |
|---|---|---|---|
| Audio capture | VB-Cable loopback + PyAudio, records a WAV file | `phase1_audio_pipeline.py`, `_simple.py` | Standalone script; **not connected** to the server. Produces a file, then transcribes the whole file. |
| Speech-to-text | OpenAI Whisper API (`whisper-1`) | `phase1_audio_pipeline.py` | Transcribes a complete audio file in one call. |
| Knowledge base | ChromaDB persistent client + embeddings | `phase2_kb_setup.py`, `chroma_data/` | Local vector store, semantic search only. |
| Validation engine | Claude Haiku (`claude-haiku-4-5-20251001`), 5-category taxonomy | `phase2_validator.py` | `validate_transcript()` processes the whole transcript at once. |
| Orchestration | `MeetingValidator.validate_meeting(transcript)` | `phase3_integration.py` | Single batch call: validate all claims → build report. |
| Storage | JSON + HTML reports under `meetings/<timestamp>/` | `phase3_storage.py` | One folder per meeting. |
| Dashboard / API | FastAPI + server-rendered HTML/JS, history side panel | `phase3_server.py` | Request/response only; no push. |

### 3.3 Current API surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Serve dashboard HTML |
| POST | `/api/validate` | Validate a full pasted transcript (synchronous) |
| GET | `/api/meetings` | List saved meetings (history panel) |
| GET | `/api/meetings/{folder_name}` | Load a saved meeting report |
| DELETE | `/api/meetings/{folder_name}` | Delete a saved meeting |
| POST | `/api/export-pdf` | Export a report to PDF |
| GET | `/api/health` | Health check |

### 3.4 Limitations that motivate this release

- **No live feedback.** The PM only learns of a contradiction *after* the meeting, when it is too late to speak up.
- **Audio is disconnected.** Capture/transcription is a separate offline script; the server only accepts pasted text.
- **Batch latency.** A full transcript is validated in one large pass — fine offline, unusable live.
- **No streaming transport.** The dashboard cannot receive updates without re-requesting.

---

## 4. Proposed Architecture (Real-Time)

### 4.1 Overview

Introduce a **streaming pipeline**: audio is captured in short chunks, transcribed incrementally, accumulated into a rolling transcript, scanned for new claims, validated, and pushed to the dashboard over a WebSocket as alerts appear. The existing batch path, storage, KB, and history panel are reused unchanged where possible.

```
                          PROPOSED (real-time, streaming)

  Meeting audio
       │
       ▼  VB-Cable loopback
  ┌──────────────────────┐   4–6s VAD chunks (HTTP/WS)     ┌──────────────────────────┐
  │ phase1_audio_         │ ──────────────────────────────►│ Real-time FastAPI server  │
  │ streaming.py          │                                 │ phase3_server_realtime.py │
  │ (chunked capture)     │                                 └────────────┬──────────────┘
  └──────────────────────┘                                               │
                                                                         ▼
                                            ┌────────────────────────────────────────────┐
                                            │  Streaming pipeline (per active session)     │
                                            │                                              │
                                            │  chunk ─► Whisper API ─► append to rolling    │
                                            │           transcript ─► claim detector ─►     │
                                            │           NEW claims only ─► Validator         │
                                            │                              (phase2, Haiku)   │
                                            │                                   │           │
                                            │                          retrieve │           │
                                            └───────────────────────────────────┼───────────┘
                                                          │                      ▼
                                                          │              ┌──────────────┐
                                              alert (WS)  │              │ ChromaDB     │
                                                          ▼              │ chroma_data/ │
  ┌──────────────────────┐   WebSocket push    ┌──────────────────────┐ └──────────────┘
  │   Browser Dashboard   │ ◄───────────────────│ phase3_websocket.py  │
  │  ┌─────────┬────────┐ │   live alerts       │ (connection manager) │
  │  │ history │ LIVE   │ │                     └──────────────────────┘
  │  │ panel   │ alerts │ │
  │  └─────────┴────────┘ │   on meeting end ──► save report ──► add to history panel
  └──────────────────────┘                          (phase3_storage.py → meetings/)
```

### 4.2 New / changed components

| Component | File | New? | Responsibility |
|---|---|---|---|
| Chunked audio streamer | `phase1_audio_streaming.py` | New | Capture audio in VAD-aligned ~4–6s chunks from VB-Cable and stream them to the server (HTTP POST or WS frames). Handle start/stop, silence gating, and reconnect. |
| WebSocket layer | `phase3_websocket.py` | New | Connection manager: register dashboard clients, broadcast alerts/status, handle disconnects and reconnection. |
| Real-time server | `phase3_server_realtime.py` | New | FastAPI app hosting: chunk-ingest endpoint, WebSocket endpoint, session lifecycle, and the existing history endpoints/side panel. |
| Streaming transcription | (in real-time server) | New | Send each chunk to Whisper API, append to a per-session rolling transcript buffer. |
| Incremental claim detector | (in validator or server) | New | Identify *new* factual claims in newly appended text only, so claims aren't re-validated. Needs an explicit claim-detection rule (see §6.3 — this was a flagged gap). |
| Validator | `phase2_validator.py` | Reuse | Validate a single claim against the KB. Add/confirm a single-claim entry point if not already exposed. |
| Knowledge base | `phase2_kb_setup.py`, `chroma_data/` | Reuse | Unchanged. |
| Storage | `phase3_storage.py` | Reuse | Save final report when session ends. |
| Orchestration | `phase3_integration.py` | Reuse / extend | Keep batch path; add a streaming-friendly per-claim path. |
| Dashboard | (in real-time server HTML) | Changed | Keep history side panel; add a live-alerts center pane fed by the WebSocket; auto-add the finished meeting to the panel. |

### 4.3 Session lifecycle

1. **Start** — PM clicks "Start live meeting." Server creates a session (id, empty transcript buffer, alert list) and opens a WebSocket to the dashboard.
2. **Stream** — Audio streamer sends VAD-aligned ~4–6s chunks. Each chunk: transcribe (primed with the prior transcript tail) → append to rolling transcript → detect new claims → validate new claims → push any alert over WS.
3. **Display** — Dashboard renders alerts live in the center pane; history panel on the left stays interactive.
4. **End** — PM clicks "End meeting." Server finalizes the transcript, builds the full report (reuse batch report generator), saves it via `phase3_storage`, and the dashboard adds it to the history panel automatically.
5. **Review** — Saved meeting is loadable/deletable exactly like today.

---

## 5. Functional Requirements

> IDs are stable references for tracking. **MUST** = required for this release; **SHOULD** = include if time permits.

### Audio & transcription

- **FR-1 (MUST)** The system shall capture meeting audio continuously via the VB-Cable loopback on Windows.
- **FR-2 (MUST)** The system shall segment audio into VAD-aligned chunks (~4–6 seconds, split on natural pauses rather than fixed time) and stream them to the server.
- **FR-3 (MUST)** The server shall transcribe each chunk via the Whisper API and append the text to a per-session rolling transcript.
- **FR-4 (SHOULD)** The system shall detect a sustained loss of audio/SNR and warn the PM ("Can't hear the meeting clearly").
- **FR-5 (MUST)** The system shall overlap consecutive chunks slightly and de-duplicate text across chunk boundaries so claims are not split or garbled. Each Whisper call shall be primed with the tail of the prior transcript via the `prompt` parameter to preserve context.
- **FR-21 (MUST)** The system shall gate capture on voice activity (VAD / silence detection), sending chunks only during active speech to protect transcription quality and control cost.

### Claim detection & validation

- **FR-6 (MUST)** The system shall detect factual claims in newly transcribed text and validate only claims not already processed in the session.
- **FR-7 (MUST)** Each claim shall be classified into exactly one of: **VERIFIED, CONTRADICTED, UNVERIFIED, OUTDATED, NEEDS_CLARIFICATION**.
- **FR-8 (MUST)** Each validation shall include the source/evidence retrieved from the KB and a confidence indicator (High/Medium/Low).
- **FR-9 (SHOULD)** The system shall handle partially-true / nuanced claims by classifying them as NEEDS_CLARIFICATION rather than forcing VERIFIED/CONTRADICTED (flagged gap — see §6.3).
- **FR-10 (MUST)** Validation shall use Claude Haiku by default to control cost/latency.

### Real-time dashboard

- **FR-11 (MUST)** The dashboard shall receive and display alerts live via WebSocket, newest-relevant first, without a page refresh.
- **FR-12 (MUST)** Each alert shall show the claim text, category (color-coded), supporting source, and a neutral suggested response for the PM.
- **FR-13 (MUST)** Alerts shall be private to the PM (local dashboard only; never broadcast into the meeting).
- **FR-14 (MUST)** The existing meeting-history side panel (list / load / delete) shall remain fully functional during and after a live session.
- **FR-15 (MUST)** On meeting end, the completed report shall be saved and automatically added to the history panel.
- **FR-16 (SHOULD)** The PM shall be able to load a past meeting while a live session is running, without disrupting the live session.
- **FR-17 (SHOULD)** The PM shall be able to dismiss/acknowledge an alert.

### Session control

- **FR-18 (MUST)** The PM shall be able to start and end a live session from the dashboard.
- **FR-19 (MUST)** Ending a session shall finalize the transcript and produce the same report format as the current batch path.
- **FR-20 (SHOULD)** The dashboard shall show live session status (listening / processing / idle) and a running claim count.

---

## 6. Non-Functional Requirements

### 6.1 Performance & latency

- **NFR-1** End-to-end latency from a *fully-spoken* claim to an on-screen alert should be **≤ 12 seconds** (target; VAD chunk ~4–6s + Whisper 2–5s + detect/validate ~1–2s). Larger chunks trade latency for boundary accuracy; revisit if the streaming-STT upgrade (§12) is adopted.
- **NFR-2** Per-claim validation latency ≤ ~1s (Haiku).
- **NFR-3** The pipeline shall keep up with continuous speech without unbounded backlog (process chunks at least as fast as they arrive; drop/merge gracefully under load).

### 6.2 Cost

- **NFR-4** Operating cost shall stay near the MVP profile: Whisper ≈ $0.02/min, Haiku ≈ $0.0001/claim → roughly **$6–15/month** for an active PM. No per-meeting cost should exceed ~$0.05.

### 6.3 Accuracy & known gaps (carried over from CRITICAL_REVIEW)

These were explicitly flagged as underspecified in the existing review and must be resolved as part of this build:

- **NFR-5 (Claim detection spec)** Define what triggers claim detection. A claim is a verifiable factual assertion about project state (status, %, dates, ownership, dependencies, decisions). Examples to flag: "QA is 80% done", "the API dependency is resolved", "we approved this on May 15". Examples to ignore: greetings, opinions without facts, logistics ("let's take a break"). Provide a prompt with positive/negative examples.
- **NFR-6 (Confidence scoring)** Define how High/Medium/Low is computed — e.g., weight by source freshness, number of agreeing/conflicting sources, and retrieval score. Crude labels alone are not acceptable for production.
- **NFR-7 (Nuanced claims)** Provide explicit handling for partially-true and temporal/judgment claims (route to NEEDS_CLARIFICATION).
- **NFR-8 (Source freshness)** Define how old a source must be to make a claim OUTDATED, and how conflicts between stale and current sources are resolved.

### 6.4 Reliability

- **NFR-9** WebSocket disconnects shall auto-reconnect; the session shall survive a brief dashboard refresh without losing accumulated alerts.
- **NFR-10** If Whisper or Claude API calls fail, the chunk shall be retried with backoff; a persistent failure surfaces a non-blocking status warning, and the session continues.
- **NFR-11** On unexpected server stop, the in-progress transcript should be recoverable (periodic buffer flush to disk).

### 6.5 Privacy & platform

- **NFR-12** All processing runs locally except Whisper and Claude API calls; no third-party meeting-platform integration.
- **NFR-13** Runs on Windows, no GPU required.
- **NFR-14** Audio is processed transiently; only the final transcript and report are persisted (raw audio chunks are not stored unless explicitly enabled).

---

## 7. Data Model

### 7.1 Claim validation result (per claim)

```json
{
  "claim_id": "string",
  "claim_text": "QA is complete",
  "category": "CONTRADICTED",                  // VERIFIED|CONTRADICTED|UNVERIFIED|OUTDATED|NEEDS_CLARIFICATION
  "confidence": "High",                        // High|Medium|Low
  "evidence": [
    { "source": "QA Tracker", "snippet": "QA at 82% as of 2026-06-14", "freshness": "2026-06-14", "score": 0.91 }
  ],
  "suggested_response": "The tracker shows QA at 82% — want to confirm the remaining 18%?",
  "timestamp": "2026-06-15T21:06:10Z"
}
```

### 7.2 Live session (in-memory, per active meeting)

```json
{
  "session_id": "string",
  "started_at": "2026-06-15T21:05:01Z",
  "status": "listening",                       // listening|processing|idle|ended
  "rolling_transcript": "string",
  "processed_claim_hashes": ["..."],           // dedupe already-validated claims
  "alerts": [ /* array of claim validation results */ ],
  "claim_count": 0
}
```

### 7.3 Stored meeting (on disk — unchanged from current)

```
meetings/<YYYY-MM-DD_HH-MM-SS>/
  transcript.txt
  report.json        // summary + validations + action_items
  report.html
```

---

## 8. API & Transport Contracts

### 8.1 New endpoints

| Method | Path | Purpose | Body / Notes |
|---|---|---|---|
| POST | `/api/session/start` | Begin a live session | → `{ session_id }` |
| POST | `/api/session/{id}/chunk` | Ingest an audio chunk | binary/multipart audio; → `202 Accepted`. (Alternative: send chunks over the WS.) |
| POST | `/api/session/{id}/end` | Finalize, build & save report | → saved `folder_name` |
| WS | `/ws/session/{id}` | Live channel: server pushes alerts & status | see message schema below |

### 8.2 Retained endpoints (unchanged)

`GET /` · `POST /api/validate` (batch fallback) · `GET /api/meetings` · `GET /api/meetings/{folder_name}` · `DELETE /api/meetings/{folder_name}` · `POST /api/export-pdf` · `GET /api/health`

### 8.3 WebSocket message schema (server → client)

```json
{ "type": "alert",  "data": { /* claim validation result, §7.1 */ } }
{ "type": "status", "data": { "status": "processing", "claim_count": 12 } }
{ "type": "ended",  "data": { "folder_name": "2026-06-15_21-05-01" } }
{ "type": "warning","data": { "message": "Audio unclear — check VB-Cable" } }
```

---

## 9. Acceptance Criteria

The release is accepted when all of the following pass:

1. **AC-1** Starting a live session and speaking a scripted contradiction (e.g., "QA is 100% done" against a KB that says 82%) produces a CONTRADICTED alert on the dashboard within ≤ 12s (per NFR-1), with the correct supporting source. *(FR-1–3, 6–8, 11, NFR-1)*
2. **AC-2** All five categories can be produced on demand from a scripted transcript, each with evidence and a confidence label. *(FR-7, 8)*
3. **AC-3** Alerts appear live over the WebSocket with no manual refresh, and the history side panel remains usable throughout. *(FR-11, 14, 16)*
4. **AC-4** Ending the session saves a `meetings/<timestamp>/` folder (transcript + report.json + report.html) and the meeting appears in the history panel automatically. *(FR-15, 19)*
5. **AC-5** A saved meeting can be loaded and deleted exactly as in the current build. *(FR-14)*
6. **AC-6** Killing and reopening the dashboard tab mid-session reconnects and retains accumulated alerts. *(NFR-9)*
7. **AC-7** A simulated Whisper/Claude API failure on one chunk does not crash the session; processing resumes on the next chunk. *(NFR-10)*
8. **AC-8** Claim-detection examples in §6.3 are validated against the implemented detector (flags the factual claims, ignores logistics/greetings). *(NFR-5)*
9. **AC-9** A full 10-minute live meeting stays within the per-meeting cost ceiling (~$0.05). *(NFR-4)*

---

## 10. Build Plan & Dependencies

### 10.1 Reuse as-is

`phase2_kb_setup.py` · `phase2_validator.py` · `phase3_integration.py` · `phase3_storage.py` · `.env` · `chroma_data/` · **the side-panel version of `phase3_server.py`** (per GEPPETTO_2_HANDOFF — do not use the older version).

### 10.2 Build new

1. `phase1_audio_streaming.py` — chunked capture + stream.
2. `phase3_websocket.py` — connection manager + broadcast.
3. `phase3_server_realtime.py` — streaming endpoints + session lifecycle + retained history endpoints + updated dashboard HTML.
4. Incremental claim detector + single-claim validator entry point (extend `phase2_validator.py` if needed).

### 10.3 Suggested order

**Spike first:** validate chunked `whisper-1` accuracy at chunk boundaries against a recorded meeting — this is the riskiest assumption in the build. Then: audio chunk streaming → server chunk-ingest + context-primed Whisper transcription → incremental claim detection → wire to validator → WebSocket push → dashboard live pane → session-end save + history integration → reliability (reconnect, retries) → acceptance pass.

### 10.4 Dependency graph

```
phase3_server_realtime.py
  ├─ phase3_websocket.py            (new)
  ├─ phase1_audio_streaming.py      (new, client-side)
  ├─ phase3_integration.py          (reuse/extend)
  │    ├─ phase2_validator.py       (reuse + per-claim path)
  │    └─ phase2_kb_setup.py        (reuse)
  ├─ phase3_storage.py              (reuse)
  └─ chroma_data/                   (reuse)
```

---

## 11. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **`whisper-1` is a batch file API, not a streaming STT** — per-request overhead and context-free short clips degrade accuracy and strain the latency target | Missed/garbled claims (hits the core function) and late alerts | **Option A (this release):** VAD-aligned ~4–6s chunks, slight overlap + de-dupe at boundaries (FR-5), and prime each call with the prior transcript tail via Whisper's `prompt` param; surface a "processing" status under load. **Planned upgrade (§12):** move to OpenAI streaming transcription (`gpt-4o-transcribe`) once the WS path is stable; local-Whisper-on-GPU remains the long-term option. |
| Chunk-boundary words split/duplicate | Garbled transcript, missed claims | Overlap chunks slightly and de-duplicate text; or use small VAD-aligned segments. |
| Over- or under-flagging claims | PM trust erosion | Lock down the claim-detection prompt with positive/negative examples (NFR-5); tune before demo. |
| Source-of-truth quality (stale KB) | Wrong alerts | Out of scope to fix, but document the dependency; freshness rules (NFR-8) reduce false OUTDATED/VERIFIED calls. |
| WebSocket churn on flaky networks | Lost alerts | Auto-reconnect + replay accumulated alerts on reconnect (NFR-9). |
| Cost creep from continuous Whisper | Budget overrun | Chunk only during active speech (VAD/silence gating); enforce per-meeting cost ceiling (NFR-4). |

---

## 12. Future (explicitly out of scope this release)

OpenAI streaming transcription (`gpt-4o-transcribe` / `-mini`) for true low-latency STT · Local Whisper on GPU (privacy + zero STT cost) · BM25 + semantic hybrid retrieval (better recall) · Haiku↔Sonnet hybrid routing for hard claims · Postgres + pgvector at scale · Electron native app · diarization · KB write-back / correction workflow with audit trail · human-in-the-loop feedback to improve validation.

---

*Source material: project_geppetto.md, GEPPETTO_2_HANDOFF.md, TECH_STACK_REVIEW.md, CRITICAL_REVIEW.md, and the phase1–phase3 implementation in this repo.*
