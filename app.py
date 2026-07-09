"""
app.py — Flask application: routes, file upload, and API endpoints.

Orchestrate mapping:
  File Upload  →  /api/upload (POST)
  ResearchAgent→  /api/chat, /api/gaps, /api/contradictions, /api/hypotheses
  Generative Prompt → handled inside agent.py (watsonx_client.generate)
  Present to User   → JSON responses consumed by the frontend
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from flask import (Flask, jsonify, render_template, request,
                   send_from_directory)
from flask_cors import CORS
from werkzeug.utils import secure_filename

from config import (AGENT_INSTRUCTIONS, FLASK_SECRET_KEY,
                    MAX_UPLOAD_MB, UPLOAD_FOLDER)
from agent import agent
from knowledge_base import kb
import watsonx_client as wx
import exa_client as exa

# ─────────────────────────────────────────────────────────────────────────────
#  Flask app setup
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = FLASK_SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
CORS(app)

ALLOWED_EXTENSIONS = {"pdf"}


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ─────────────────────────────────────────────────────────────────────────────
#  HTML views
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html",
                            domain=AGENT_INSTRUCTIONS["domain"],
                            citation_style=AGENT_INSTRUCTIONS["citation_style"])


# ─────────────────────────────────────────────────────────────────────────────
#  API — System status
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    return jsonify({
        "watsonx": wx.is_configured(),
        "exa": exa.is_configured(),
        "domain": AGENT_INSTRUCTIONS["domain"],
        "citation_style": AGENT_INSTRUCTIONS["citation_style"],
        "react_max_steps": AGENT_INSTRUCTIONS["react_max_steps"],
        "model": "ibm/granite-3-3-8b-instruct",
        "timestamp": time.time(),
    })


# ─────────────────────────────────────────────────────────────────────────────
#  API — Knowledge base / file upload
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def api_upload():
    """
    Orchestrate node: File Upload
    Accepts one or more PDF files.  Optional form field: is_test_case=true
    """
    if "files" not in request.files:
        return jsonify({"error": "No files field in request"}), 400

    files = request.files.getlist("files")
    is_test = request.form.get("is_test_case", "false").lower() == "true"
    results = []

    for f in files:
        if not f or not f.filename:
            continue
        if not _allowed(f.filename):
            results.append({"filename": f.filename, "status": "rejected",
                             "reason": "Only PDF files accepted"})
            continue

        safe_name = secure_filename(f.filename)
        # Prepend UUID to avoid collisions
        dest = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}_{safe_name}")
        f.save(dest)

        try:
            embed_fn = wx.embed if wx.is_configured() else None
            record = kb.add_paper(dest, safe_name, embed_fn=embed_fn,
                                   is_test_case=is_test)
            results.append({
                "filename": safe_name,
                "status": "ingested",
                "sha256": record["sha256"],
                "title": record["title"],
                "authors": record["authors"],
                "year": record["year"],
                "chunks": len(record["chunks"]),
                "is_test_case": is_test,
            })
        except Exception as exc:
            results.append({"filename": safe_name, "status": "error",
                             "reason": str(exc)})

    return jsonify({"uploaded": len(results), "results": results})


@app.route("/api/papers", methods=["GET"])
def api_papers():
    """List all papers in the knowledge base."""
    return jsonify({"papers": kb.list_papers()})


@app.route("/api/papers/<sha256>", methods=["DELETE"])
def api_delete_paper(sha256: str):
    """Remove a paper from the knowledge base."""
    removed = kb.remove_paper(sha256)
    return jsonify({"removed": removed})


# ─────────────────────────────────────────────────────────────────────────────
#  API — Research Agent (Orchestrate: ResearchAgent + Generative Prompt)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Main ReAct chat endpoint.
    Body: { "query": "...", "use_web": true }
    Returns: AgentResponse as JSON.
    """
    body = request.get_json(silent=True) or {}
    query = (body.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400

    use_web = body.get("use_web", True)
    resp = agent.query(query, use_web=use_web)

    return jsonify({
        "query": resp.query,
        "steps": [
            {
                "step_type": s.step_type,
                "content": s.content,
                "tool": s.tool,
                "source": s.source,
                "confidence": s.confidence,
            }
            for s in resp.steps
        ],
        "final_answer": resp.final_answer,
        "citations": resp.citations,
        "elapsed_s": resp.elapsed_s,
    })


@app.route("/api/gaps", methods=["GET"])
def api_gaps():
    """Run gap analysis across all uploaded papers."""
    gaps = agent.gap_analysis()
    return jsonify({"gaps": gaps})


@app.route("/api/contradictions", methods=["GET"])
def api_contradictions():
    """Detect contradictions between uploaded papers."""
    contradictions = agent.contradiction_detection()
    return jsonify({"contradictions": contradictions})


@app.route("/api/hypotheses", methods=["POST"])
def api_hypotheses():
    """
    Generate hypotheses for a topic.
    Body: { "topic": "..." }
    """
    body = request.get_json(silent=True) or {}
    topic = (body.get("topic") or AGENT_INSTRUCTIONS["domain"]).strip()
    hypotheses = agent.generate_hypotheses(topic)
    return jsonify({"hypotheses": hypotheses, "topic": topic})


@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    """Return dashboard summary (paper count, config, etc.)."""
    return jsonify(agent.dashboard_summary())


@app.route("/api/cite", methods=["POST"])
def api_cite():
    """
    Format a citation on demand.
    Body: { "papers": [{ "title": "...", "authors": "...", "year": "..." }], "style": "IEEE" }
    """
    body = request.get_json(silent=True) or {}
    papers = body.get("papers", [])
    style  = body.get("style", AGENT_INSTRUCTIONS["citation_style"])
    from agent import _format_citation
    citations = [_format_citation(p, i + 1, style) for i, p in enumerate(papers)]
    return jsonify({"citations": citations})


# ─────────────────────────────────────────────────────────────────────────────
#  Static file serving
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)


# ─────────────────────────────────────────────────────────────────────────────
#  Error handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": f"File too large (max {MAX_UPLOAD_MB} MB)"}), 413


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error", "detail": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug, port=5000, host="0.0.0.0")
