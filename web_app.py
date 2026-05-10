#!/usr/bin/env python3
"""Resume Generator — Web UI.

A Flask app that lets you paste a job URL and generates
a tailored resume, cover letter, and outreach materials.
Files are uploaded to Google Drive after generation.

Usage:
    # Local dev:
    python web_app.py

    # Production (gunicorn):
    gunicorn web_app:app -w 4 --threads 4 -b 0.0.0.0:5050 --timeout 600

    # Pre-fill URL from email link:
    https://your-server.com/?url=https://jobs.lever.co/company/abc123&role=PM
"""

import json
import os
import queue
import sys
import threading
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__)

# In-memory store for job progress/results (keyed by job_id)
_jobs: dict[str, dict] = {}
_job_logs: dict[str, queue.Queue] = {}


class _LogCapture:
    """Redirect print() output to an SSE queue during pipeline execution."""

    def __init__(self, q: queue.Queue, original):
        self.q = q
        self.original = original

    def write(self, msg):
        if msg.strip():
            self.q.put(("log", msg.strip()))
        self.original.write(msg)

    def flush(self):
        self.original.flush()


def _upload_to_drive(output_dir: str, folder_parts: list[str] | None, log_q: queue.Queue) -> dict:
    """Upload generated files to Google Drive."""
    try:
        from drive_uploader import upload_output_dir
        log_q.put(("status", "Uploading to Google Drive..."))
        links = upload_output_dir(output_dir, folder_parts=folder_parts)
        log_q.put(("status", f"Uploaded {len(links)} file(s) to Drive"))
        return links
    except Exception as e:
        log_q.put(("log", f"Drive upload failed: {e}"))
        return {}


def _run_pipeline(job_id: str, url: str, role_type: str, jd_text: str = ""):
    """Run the resume generation pipeline in a background thread."""
    log_q = _job_logs[job_id]

    # Capture stdout so we can stream progress
    old_stdout = sys.stdout
    sys.stdout = _LogCapture(log_q, old_stdout)

    try:
        if jd_text.strip():
            log_q.put(("status", f"Using pasted JD ({len(jd_text)} chars). Starting pipeline..."))
        else:
            _jobs[job_id]["status"] = "scraping"
            log_q.put(("status", "Scraping job description..."))

            from scraper import scrape_jd
            jd_text = scrape_jd(url)

            if not jd_text or len(jd_text) < 50:
                # Fallback to the simple fetch from main.py
                from main import fetch_url
                jd_text = fetch_url(url)

            if not jd_text.strip() or len(jd_text.strip()) < 50:
                raise ValueError("Could not extract job description from this URL. Try pasting the JD text directly in the text field below.")

        log_q.put(("status", f"JD loaded ({len(jd_text)} chars). Starting pipeline..."))
        _jobs[job_id]["status"] = "generating"

        from orchestrator import run
        job_meta = {"role_url": url} if url else {}
        results = run(jd_text=jd_text, role_type=role_type, job_meta=job_meta)

        # Upload to Google Drive
        _jobs[job_id]["status"] = "uploading"
        drive_links = _upload_to_drive(
            results.get("output_dir", ""),
            results.get("folder_parts"),
            log_q,
        )
        results["drive_links"] = drive_links

        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["results"] = results
        log_q.put(("status", "Done!"))
        log_q.put(("done", json.dumps(results, default=str)))

    except Exception as e:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(e)
        log_q.put(("error", str(e)))

    finally:
        sys.stdout = old_stdout
        log_q.put(("end", ""))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    url = data.get("url", "").strip()
    jd_text = data.get("jd_text", "").strip()
    role_type = data.get("role_type", "PM").strip().upper()

    if not url and not jd_text:
        return jsonify({"error": "Provide a URL or paste the job description"}), 400

    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"status": "queued", "url": url, "role_type": role_type}
    _job_logs[job_id] = queue.Queue()

    thread = threading.Thread(target=_run_pipeline, args=(job_id, url, role_type, jd_text), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id):
    """SSE endpoint — streams log lines and status updates."""
    if job_id not in _job_logs:
        return "Job not found", 404

    def event_stream():
        log_q = _job_logs[job_id]
        while True:
            try:
                event_type, data = log_q.get(timeout=120)
                yield f"event: {event_type}\ndata: {data}\n\n"
                if event_type in ("done", "error", "end"):
                    break
            except queue.Empty:
                yield "event: ping\ndata: keepalive\n\n"

    return Response(event_stream(), mimetype="text/event-stream")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, threaded=True)
