"""
PHASE 3: FASTAPI SERVER & DASHBOARD
====================================
Main server that:
1. Orchestrates Phase 1 + 2
2. Serves the interactive dashboard
3. Provides API endpoints for validation

Usage:
  pip install fastapi uvicorn
  python phase3_server.py

Then open: http://localhost:8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel
import uvicorn
from phase3_integration import get_validator
from phase3_storage import get_storage

# ============================================================================
# FASTAPI APP SETUP
# ============================================================================

app = FastAPI(title="Meeting Truth Layer", version="1.0")

# ============================================================================
# DATA MODELS
# ============================================================================

class TranscriptRequest(BaseModel):
    """Request body for transcript validation."""
    transcript: str


class ValidationResponse(BaseModel):
    """Response from validation endpoint."""
    summary: dict
    validations: list
    action_items: list


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Serve the dashboard HTML."""
    return HTMLResponse(get_dashboard_html())


@app.post("/api/validate")
async def validate_transcript(request: TranscriptRequest):
    """
    Validate a meeting transcript.

    Returns structured validation with:
    - Summary (counts by category)
    - All validations
    - Action items sorted by priority
    """
    try:
        if not request.transcript.strip():
            raise HTTPException(status_code=400, detail="Transcript cannot be empty")

        validator = get_validator()
        report = validator.validate_meeting(request.transcript)

        # Save to file automatically
        storage = get_storage()
        saved_info = storage.save_meeting(request.transcript, report)

        return JSONResponse({
            "success": True,
            "summary": report['summary'],
            "validations": report['validations'],
            "action_items": report['action_items'],
            "saved_to": saved_info,
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/meetings")
async def list_meetings():
    """
    List all saved meetings.

    Returns list of meetings with summary stats.
    """
    try:
        storage = get_storage()
        meetings = storage.list_meetings()
        return JSONResponse({
            "success": True,
            "meetings": meetings,
            "total": len(meetings)
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/meetings/{folder_name}")
async def get_meeting(folder_name: str):
    """
    Load a specific saved meeting.

    Args:
        folder_name: Name of the meeting folder (e.g., "2025-06-15_14-30-45")
    """
    try:
        storage = get_storage()
        meeting = storage.load_meeting(folder_name)
        return JSONResponse({
            "success": True,
            "transcript": meeting['transcript'],
            "report": meeting['report']
        })
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Meeting {folder_name} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/meetings/{folder_name}")
async def delete_meeting(folder_name: str):
    """
    Delete a saved meeting.

    Args:
        folder_name: Name of the meeting folder to delete
    """
    try:
        import shutil
        storage = get_storage()
        meeting_path = storage.base_dir / folder_name

        if not meeting_path.exists():
            raise HTTPException(status_code=404, detail=f"Meeting {folder_name} not found")

        shutil.rmtree(meeting_path)
        return JSONResponse({
            "success": True,
            "message": f"Meeting {folder_name} deleted"
        })
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Meeting {folder_name} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/export-pdf")
async def export_pdf(request: TranscriptRequest):
    """
    Export validation as HTML (can be printed to PDF).
    """
    try:
        validator = get_validator()
        report = validator.validate_meeting(request.transcript)
        html = validator._generate_html_report(report)
        return HTMLResponse(html)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "Meeting Truth Layer"}


# ============================================================================
# DASHBOARD HTML
# ============================================================================

def get_dashboard_html():
    """Return the interactive dashboard HTML."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Meeting Truth Layer - Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 0;
            display: flex;
        }

        .sidebar {
            width: 280px;
            background: white;
            box-shadow: 2px 0 10px rgba(0,0,0,0.1);
            overflow-y: auto;
            padding: 20px;
        }

        .sidebar h2 {
            color: #333;
            font-size: 1.1em;
            margin-bottom: 15px;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }

        .meeting-item {
            background: #f9f9f9;
            padding: 12px;
            margin-bottom: 10px;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.2s;
            border-left: 3px solid #667eea;
        }

        .meeting-item:hover {
            background: #f0f0f0;
            transform: translateX(5px);
        }

        .meeting-name {
            font-weight: 600;
            color: #333;
            font-size: 0.9em;
            margin-bottom: 5px;
        }

        .meeting-stats {
            font-size: 0.8em;
            color: #666;
            margin-bottom: 8px;
        }

        .meeting-actions {
            display: flex;
            gap: 5px;
        }

        .btn-load {
            flex: 1;
            padding: 6px 8px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 3px;
            font-size: 0.75em;
            cursor: pointer;
        }

        .btn-load:hover {
            background: #5568d3;
        }

        .btn-delete {
            padding: 6px 8px;
            background: #dc3545;
            color: white;
            border: none;
            border-radius: 3px;
            font-size: 0.75em;
            cursor: pointer;
        }

        .btn-delete:hover {
            background: #c82333;
        }

        .no-meetings {
            text-align: center;
            color: #999;
            padding: 20px;
            font-size: 0.9em;
        }

        .main-content {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        header {
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }

        h1 {
            color: #333;
            margin-bottom: 10px;
        }

        .subtitle {
            color: #666;
            font-size: 0.95em;
        }

        .dashboard-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }

        @media (max-width: 900px) {
            .dashboard-grid {
                grid-template-columns: 1fr;
            }

            .sidebar {
                width: 100%;
                margin-bottom: 20px;
            }

            body {
                flex-direction: column;
            }
        }

        .card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }

        .card h2 {
            color: #333;
            margin-bottom: 15px;
            font-size: 1.2em;
        }

        textarea {
            width: 100%;
            height: 250px;
            padding: 15px;
            border: 2px solid #e0e0e0;
            border-radius: 5px;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 0.9em;
            resize: vertical;
        }

        textarea:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .button-group {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }

        button {
            flex: 1;
            padding: 12px 20px;
            border: none;
            border-radius: 5px;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .btn-validate {
            background: #667eea;
            color: white;
        }

        .btn-validate:hover {
            background: #5568d3;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }

        .btn-validate:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }

        .btn-export {
            background: #48bb78;
            color: white;
        }

        .btn-export:hover {
            background: #38a169;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(72, 187, 120, 0.4);
        }

        .btn-export:disabled {
            background: #ccc;
            cursor: not-allowed;
        }

        .loading {
            text-align: center;
            color: #667eea;
            display: none;
        }

        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
            margin: 0 auto 10px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
        }

        .stat-card {
            background: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            text-align: center;
            border: 2px solid #e0e0e0;
        }

        .stat-number {
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }

        .stat-label {
            color: #666;
            font-size: 0.9em;
            margin-top: 5px;
        }

        .results {
            display: none;
        }

        .action-items {
            margin: 20px 0;
        }

        .action-item {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 10px 0;
            border-radius: 3px;
        }

        .action-item.critical {
            background: #f8d7da;
            border-left-color: #dc3545;
        }

        .action-item.high {
            background: #fff3cd;
            border-left-color: #ffc107;
        }

        .action-item.medium {
            background: #d1ecf1;
            border-left-color: #17a2b8;
        }

        .action-priority {
            display: inline-block;
            background: #333;
            color: white;
            padding: 4px 8px;
            border-radius: 3px;
            font-weight: bold;
            font-size: 0.85em;
            margin-right: 10px;
        }

        .validations-list {
            max-height: 400px;
            overflow-y: auto;
        }

        .validation {
            background: #f9f9f9;
            padding: 12px;
            margin: 10px 0;
            border-left: 4px solid #ccc;
            border-radius: 3px;
        }

        .validation.verified {
            border-left-color: #28a745;
        }

        .validation.contradicted {
            border-left-color: #dc3545;
        }

        .validation.unverified {
            border-left-color: #ffc107;
        }

        .validation.outdated {
            border-left-color: #6c757d;
        }

        .validation.needs-clarification {
            border-left-color: #17a2b8;
        }

        .validation-category {
            font-weight: bold;
            margin-bottom: 5px;
        }

        .validation-claim {
            font-style: italic;
            color: #555;
            font-size: 0.95em;
            margin: 5px 0;
        }

        .validation-confidence {
            font-size: 0.85em;
            color: #666;
        }

        .no-results {
            text-align: center;
            color: #999;
            padding: 40px 20px;
        }

        .timestamp {
            color: #999;
            font-size: 0.85em;
        }

        footer {
            text-align: center;
            color: white;
            margin-top: 40px;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <!-- SIDEBAR: History Panel -->
    <div class="sidebar">
        <h2>📋 History</h2>
        <div id="meetingsList" class="no-meetings">Loading...</div>
    </div>

    <!-- MAIN CONTENT -->
    <div class="main-content">
        <div class="container">
            <header>
                <h1>📊 Meeting Truth Layer</h1>
                <p class="subtitle">Real-time meeting validation dashboard</p>
            </header>

            <div class="dashboard-grid">
            <!-- Input Card -->
            <div class="card">
                <h2>📝 Meeting Transcript</h2>
                <textarea id="transcript" placeholder="Paste your meeting transcript here...
Example: CEO: 'When is the release?'
Engineering: 'June 21 is locked in.'
Product: 'All features are approved.'"></textarea>
                <div class="button-group">
                    <button class="btn-validate" onclick="validateTranscript()">Validate</button>
                    <button class="btn-export" onclick="exportPDF()" disabled id="exportBtn">Export PDF</button>
                </div>
                <div class="loading" id="loading">
                    <div class="spinner"></div>
                    <p>Validating claims...</p>
                </div>
            </div>

            <!-- Summary Card -->
            <div class="card results" id="summaryCard">
                <h2>📊 Summary</h2>
                <div class="summary-grid" id="summaryGrid"></div>
                <p class="timestamp" id="timestamp" style="margin-top: 15px;"></p>
            </div>
        </div>

        <!-- Action Items Card -->
        <div class="card results" id="actionsCard" style="display: none;">
            <h2>🎯 Action Items</h2>
            <div class="action-items" id="actionItems"></div>
        </div>

        <!-- Validations Card -->
        <div class="card results" id="validationsCard" style="display: none;">
            <h2>📋 All Validations</h2>
            <div class="validations-list" id="validationsList"></div>
        </div>

            <footer>
                <p>Meeting Truth Layer v1.0 | Powered by Phase 1, 2, and 3</p>
            </footer>
        </div>
    </div>

    <script>
        const categoryIcons = {
            'VERIFIED': '🟢',
            'CONTRADICTED': '🔴',
            'UNVERIFIED': '🟡',
            'OUTDATED': '⏰',
            'NEEDS_CLARIFICATION': '❓'
        };

        // Load meetings list on page load
        window.addEventListener('load', loadMeetings);

        async function loadMeetings() {
            try {
                const response = await fetch('/api/meetings');
                const data = await response.json();

                if (data.meetings.length === 0) {
                    document.getElementById('meetingsList').innerHTML = '<div class="no-meetings">No meetings yet</div>';
                    return;
                }

                const html = data.meetings.map(meeting => `
                    <div class="meeting-item">
                        <div class="meeting-name">${meeting.name}</div>
                        <div class="meeting-stats">
                            ${meeting.total_claims} claims |
                            🟢 ${meeting.verified} |
                            🔴 ${meeting.contradicted}
                        </div>
                        <div class="meeting-actions">
                            <button class="btn-load" onclick="loadMeeting('${meeting.name}')">Load</button>
                            <button class="btn-delete" onclick="deleteMeeting('${meeting.name}')">Delete</button>
                        </div>
                    </div>
                `).join('');

                document.getElementById('meetingsList').innerHTML = html;
            } catch (error) {
                console.error('Error loading meetings:', error);
                document.getElementById('meetingsList').innerHTML = '<div class="no-meetings">Error loading history</div>';
            }
        }

        async function loadMeeting(folderName) {
            try {
                const response = await fetch(`/api/meetings/${folderName}`);
                const data = await response.json();

                // Populate transcript
                document.getElementById('transcript').value = data.transcript;

                // Display results
                displayResults(data.report);

                // Scroll to top
                window.scrollTo(0, 0);
            } catch (error) {
                alert('Error loading meeting: ' + error.message);
            }
        }

        async function deleteMeeting(folderName) {
            if (!confirm(`Delete meeting "${folderName}"? This cannot be undone.`)) {
                return;
            }

            try {
                const response = await fetch(`/api/meetings/${folderName}`, {
                    method: 'DELETE'
                });

                if (response.ok) {
                    alert('Meeting deleted');
                    loadMeetings(); // Refresh list
                } else {
                    alert('Error deleting meeting');
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }

        async function validateTranscript() {
            const transcript = document.getElementById('transcript').value.trim();

            if (!transcript) {
                alert('Please enter a transcript');
                return;
            }

            // Show loading
            document.getElementById('loading').style.display = 'block';
            document.getElementById('summaryCard').style.display = 'none';
            document.getElementById('actionsCard').style.display = 'none';
            document.getElementById('validationsCard').style.display = 'none';

            try {
                const response = await fetch('/api/validate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ transcript })
                });

                if (!response.ok) throw new Error('Validation failed');

                const data = await response.json();
                displayResults(data);
            } catch (error) {
                alert('Error: ' + error.message);
            } finally {
                document.getElementById('loading').style.display = 'none';
            }
        }

        function displayResults(data) {
            const summary = data.summary;
            const validations = data.validations;
            const actionItems = data.action_items;

            // Summary Grid
            const summaryHTML = `
                <div class="stat-card">
                    <div class="stat-number">${summary.total_claims}</div>
                    <div class="stat-label">Total Claims</div>
                </div>
                <div class="stat-card" style="color: #28a745;">
                    <div class="stat-number">🟢 ${summary.verified}</div>
                    <div class="stat-label">Verified</div>
                </div>
                <div class="stat-card" style="color: #dc3545;">
                    <div class="stat-number">🔴 ${summary.contradicted}</div>
                    <div class="stat-label">Contradicted</div>
                </div>
                <div class="stat-card" style="color: #ffc107;">
                    <div class="stat-number">🟡 ${summary.unverified}</div>
                    <div class="stat-label">Unverified</div>
                </div>
                <div class="stat-card" style="color: #6c757d;">
                    <div class="stat-number">⏰ ${summary.outdated}</div>
                    <div class="stat-label">Outdated</div>
                </div>
                <div class="stat-card" style="color: #17a2b8;">
                    <div class="stat-number">❓ ${summary.needs_clarification}</div>
                    <div class="stat-label">Need Clarification</div>
                </div>
            `;

            document.getElementById('summaryGrid').innerHTML = summaryHTML;
            document.getElementById('timestamp').textContent = 'Generated: ' + new Date(summary.timestamp).toLocaleString();
            document.getElementById('summaryCard').style.display = 'block';

            // Action Items
            if (actionItems.length > 0) {
                const actionsHTML = actionItems.map(item => `
                    <div class="action-item ${item.priority.toLowerCase()}">
                        <span class="action-priority">${item.priority}</span>
                        <strong>${item.action}</strong><br>
                        <small><em>"${item.claim}"</em><br>
                        ${item.reasoning}</small>
                    </div>
                `).join('');
                document.getElementById('actionItems').innerHTML = actionsHTML;
                document.getElementById('actionsCard').style.display = 'block';
            }

            // Validations
            const validationsHTML = validations.map(v => `
                <div class="validation ${v.category.toLowerCase().replace('_', '-')}">
                    <div class="validation-category">
                        ${categoryIcons[v.category]} ${v.category}
                    </div>
                    <div class="validation-claim">"${v.claim}"</div>
                    <div class="validation-confidence">
                        Confidence: ${(v.confidence * 100).toFixed(0)}%
                    </div>
                    <small>${v.reasoning}</small>
                </div>
            `).join('');
            document.getElementById('validationsList').innerHTML = validationsHTML;
            document.getElementById('validationsCard').style.display = 'block';

            // Enable export
            document.getElementById('exportBtn').disabled = false;
        }

        async function exportPDF() {
            const transcript = document.getElementById('transcript').value.trim();
            if (!transcript) {
                alert('Please enter a transcript first');
                return;
            }

            try {
                const response = await fetch('/api/export-pdf', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ transcript })
                });

                if (!response.ok) throw new Error('Export failed');

                const html = await response.text();
                const printWindow = window.open('', '', 'height=600,width=800');
                printWindow.document.write(html);
                printWindow.document.close();
                printWindow.print();
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }
    </script>
</body>
</html>
"""


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("\n" + "█" * 70)
    print("█" + " " * 68 + "█")
    print("█" + "  PHASE 3: MEETING TRUTH LAYER SERVER".center(68) + "█")
    print("█" + " " * 68 + "█")
    print("█" * 70)

    print("\n📡 Starting server...\n")
    print("✅ Open http://localhost:8000 in your browser")
    print("✅ Paste a meeting transcript")
    print("✅ Click 'Validate' to see results")
    print("\n" + "=" * 70 + "\n")

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
