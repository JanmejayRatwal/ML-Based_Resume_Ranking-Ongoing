# main.py — Flask server replacing the pywebview JS bridge
# Runs Flask on localhost:5000; pywebview opens index.html pointing at it.
# File dialog uses tkinter (works independently of the JS bridge).

import tempfile
import os
import sys
import json
import csv
import logging
import threading
import subprocess
from pathlib import Path
from functools import partial
from multiprocessing import Pool

import tkinter as tk
from tkinter import filedialog

import webview
from flask import Flask, request, jsonify
from flask_cors import CORS

from batch import create_batches
from ranker import process_batch, merge_results
from output_writer import write_output
from honeypot_filter import detect_honeypots, is_honeypot
from rule_based_judge import generate_explanations

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
SAMPLE_FILE = str(BASE_DIR / "sample_candidates.json")
FULL_FILE = str(BASE_DIR / "candidates.jsonl")
OUTPUT_DIR = BASE_DIR / "output"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(
            __file__), "log", "candidateranker.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(
    __name__,
    static_folder=".",
    static_url_path=""
)
CORS(app)  # allow the webview origin to call localhost:5000


@app.route("/")
def index():
    return app.send_static_file("index.html")


# Module-level state (single-user desktop app — no session needed)
_state = {
    "last_csv":  "",
    "last_file": "",
}


# ── Helper: normalise .json array or .jsonl to a temp JSONL file ──────────────

def _to_jsonl(src_path):
    src = Path(src_path)
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl",
                                      delete=False, encoding="utf-8")
    if src.suffix == ".json":
        with open(src, encoding="utf-8") as f:
            candidates = json.load(f)
        if isinstance(candidates, dict):
            candidates = candidates.get("candidates", [])
        for c in candidates:
            tmp.write(json.dumps(c) + "\n")
    else:
        with open(src, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    tmp.write(line + "\n")
    tmp.close()
    return tmp.name


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/api/open_file_dialog", methods=["POST"])
def open_file_dialog():
    """Open a native tkinter file-picker and return the chosen path."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(
        title="Select candidate file",
        filetypes=[("JSON / JSONL files", "*.json *.jsonl")],
    )
    root.destroy()
    if path:
        _state["last_file"] = path
        return jsonify({"path": path})
    return jsonify({"path": None})


@app.route("/api/upload_file", methods=["POST"])
def upload_file():
    """Accept a drag-and-dropped file, save it to a temp location, return its path."""
    f = request.files.get("file")
    if not f:
        return jsonify({"status": "error", "message": "No file received"}), 400
    suffix = Path(f.filename).suffix or ".jsonl"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    f.save(tmp.name)
    tmp.close()
    _state["last_file"] = tmp.name
    return jsonify({"path": tmp.name})


@app.route("/api/start_ranking", methods=["POST"])
def start_ranking():
    """Rank the given file and return results synchronously (runs in Flask worker thread)."""
    body = request.get_json(force=True) or {}
    file_path = body.get("file_path") or _state["last_file"]
    weights = body.get("weights") or {}
    filters = body.get("filters") or {}

    if not file_path:
        return jsonify({"status": "error", "message": "No file selected."}), 400

    _state["last_file"] = file_path

    try:
        result = _run_ranking(file_path, weights, filters)
        return jsonify(result)
    except Exception as e:
        logger.error("Ranking failed: %s", e, exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/open_csv", methods=["POST"])
def open_csv():
    """Open the last exported CSV in the system default application."""
    path = _state["last_csv"]
    if not path or not os.path.exists(path):
        return jsonify({"status": "error", "message": "No CSV available yet."}), 404
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ── Core ranking pipeline ─────────────────────────────────────────────────────

def _run_ranking(file_path, weights, filters):
    tmp_path = None
    try:
        logger.info("Ranking started — %s", file_path)

        # Step 1: normalise to JSONL
        tmp_path = _to_jsonl(file_path)

        # Step 2: batch → parallel score → merge (2× buffer for honeypot removal)
        batches = create_batches(tmp_path, num_batches=4)
        worker = partial(process_batch, weights=weights)
        with Pool(processes=4) as pool:
            results = pool.map(worker, batches)
        top_buffer = merge_results(results, top_n=200)

        # Step 3: strip honeypots; keep exactly 100 clean candidates
        honeypot_count = sum(1 for _, c in top_buffer if is_honeypot(c))
        top100_clean = [(s, c)
                        for s, c in top_buffer if not is_honeypot(c)][:100]
        logger.info("Honeypots removed: %d → %d clean candidates",
                    honeypot_count, len(top100_clean))

        # Step 4: generate reasons for top 100
        logger.info("Generating reasons for %d candidates...",
                    len(top100_clean))
        reasons_data = generate_explanations(top100_clean)
        logger.info("Reasons generated successfully")

        # Step 5: save CSV
        OUTPUT_DIR.mkdir(exist_ok=True)
        from datetime import datetime
        csv_path = str(
            OUTPUT_DIR / f"top100_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        reasons_only = [reason for reason, _ in reasons_data]
        write_output(top100_clean, csv_path, reasons_only)
        _state["last_csv"] = csv_path
        logger.info("Saved top 100 to %s", csv_path)

        # Step 6: build ranked payload
        ranked = []
        for idx, (score_val, candidate) in enumerate(top100_clean):
            reason, breakdown = reasons_data[idx] if idx < len(
                reasons_data) else ("Strong candidate profile.", {})
            ranked.append({
                "candidate":       candidate,
                "score":           round(float(score_val), 4),
                "breakdown":       breakdown,
                "reason":          reason,
                "honeypotReasons": [],
            })

        stats = {
            "total":    len(top_buffer),
            "honeypots": honeypot_count,
            "topFit":   sum(1 for r in ranked if r["score"] >= 0.65),
            "avgScore": round(sum(r["score"] for r in ranked) / len(ranked), 4) if ranked else 0,
        }

        return {
            "status": "ok",
            "ranked": ranked,
            "count":  len(ranked),
            "stats":  stats,
        }

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Entry point ───────────────────────────────────────────────────────────────

def _start_flask():
    """Run Flask in a background daemon thread."""
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    # Start Flask server in the background
    flask_thread = threading.Thread(target=_start_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask server started on http://127.0.0.1:5000")

    # Open pywebview window pointing at the Flask-served page.
    # No js_api needed — the browser talks to Flask directly via fetch().
    window = webview.create_window(
        "CandidateRanker",
        "http://127.0.0.1:5000/",   # serve index.html from Flask, or keep "index.html"
        width=1280, height=820, min_size=(900, 600),
    )

    # webview.start() must run on the main thread
    webview.start(debug=True)
