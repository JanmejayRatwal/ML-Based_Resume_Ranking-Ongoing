# Not to be used yet, it's for final implementation,
# Used Ai for creation

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

import webview
from batch import create_batches
from ranker import process_batch, merge_results
from output_writer import write_output
from honeypot_filter import detect_honeypots, is_honeypot

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent
SAMPLE_FILE = str(BASE_DIR / "sample_candidates.json")
FULL_FILE   = str(BASE_DIR / "candidates.jsonl")
OUTPUT_DIR  = BASE_DIR / "output"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "log", "candidateranker.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ── Helper: load a .json array or .jsonl file into a temp JSONL ───────────────
import tempfile

def _to_jsonl(src_path):
    """Converts a JSON array file or JSONL file into a temp JSONL file."""
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
    else:                               # already JSONL
        with open(src, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    tmp.write(line + "\n")
    tmp.close()
    return tmp.name


class API:

    def __init__(self):
        self.window     = None
        self._last_csv  = ""
        self._last_file = ""

    def set_window(self, w):
        self.window = w

    # ── Called by app.js: load a preset and rank it ───────────────────────────
    def load_preset(self, preset: str):
        """preset = 'sample'  or  '100k'"""
        self._last_file = SAMPLE_FILE if preset == "sample" else FULL_FILE
        self.start_ranking(self._last_file)

    # ── Called by app.js: open a native file-picker dialog ────────────────────
    def open_file_dialog(self):
        result = self.window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("JSON JSONL files (*.json;*.jsonl)",),
        )
        if result:
            self._last_file = result[0]
            return result[0]
        return None

    # ── Called by app.js: rank the loaded file ────────────────────────────────
    def start_ranking(self, file_path: str = "",
                      weights_json: str = "{}", filters_json: str = "{}"):
        path    = file_path or self._last_file
        weights = json.loads(weights_json) if weights_json else {}
        filters = json.loads(filters_json) if filters_json else {}

        if not path:
            self._send_error("No file selected.")
            return

        # Run the ranking in the background so the UI doesn't freeze
        thread = threading.Thread(
            target=self._run_ranking,
            args=(path, weights, filters),
            daemon=True,
        )
        thread.start()

    # ── Called by app.js: open the last exported CSV ──────────────────────────
    def open_csv(self):
        if not self._last_csv or not os.path.exists(self._last_csv):
            self._send_error("No CSV available yet.")
            return
        try:
            if sys.platform == "win32":
                os.startfile(self._last_csv)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self._last_csv])
            else:
                subprocess.Popen(["xdg-open", self._last_csv])
        except Exception as e:
            self._send_error(f"Could not open CSV: {e}")

    # ── Internal: full ranking pipeline (runs in a background thread) ─────────
    def _run_ranking(self, file_path, weights, filters):
        tmp_path = None
        try:
            logger.info("Ranking started — %s", file_path)

            # Step 1: normalise to JSONL so create_batches() can read it
            tmp_path = _to_jsonl(file_path)

            # Step 2: batch → parallel score → merge (fetch extra buffer for honeypot removal)
            batches = create_batches(tmp_path, num_batches=4)
            worker  = partial(process_batch, weights=weights)
            with Pool(processes=4) as pool:
                results = pool.map(worker, batches)
            top_buffer = merge_results(results, top_n=200)   # fetch 2× to absorb honeypots

            # Step 3: save CSV
            OUTPUT_DIR.mkdir(exist_ok=True)
            from datetime import datetime
            csv_path = str(OUTPUT_DIR / f"top100_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            write_output(top_buffer[:100], csv_path)
            self._last_csv = csv_path
            logger.info("Done — buffer %d, saved to %s", len(top_buffer), csv_path)

            # Step 4: always strip honeypots; keep exactly 100 clean candidates
            honeypot_count = sum(1 for _, c in top_buffer if is_honeypot(c))
            top100_clean   = [(s, c) for s, c in top_buffer if not is_honeypot(c)][:100]
            logger.info("Honeypots removed: %d → %d clean candidates", honeypot_count, len(top100_clean))

            # Step 5: build result records and send back to JS
            ranked = []
            for score_val, candidate in top100_clean:
                profile = candidate.get("profile", {}) or {}
                ranked.append({
                    "candidate":       candidate,
                    "score":           round(float(score_val), 4),
                    "breakdown":       {"badges": [], "matched_skills": []},
                    "reason":          f"{profile.get('anonymized_name','Candidate')} scored {score_val:.2f}.",
                    "honeypotReasons": [],
                })

            stats = {
                "total":    len(top_buffer),
                "honeypots": honeypot_count,
                "topFit":   sum(1 for r in ranked if r["score"] >= 0.65),
                "avgScore": round(sum(r["score"] for r in ranked) / len(ranked), 4) if ranked else 0,
            }
            self._send_results(ranked, stats)

        except Exception as e:
            logger.error("Ranking failed: %s", e, exc_info=True)
            self._send_error(str(e))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ── Internal: push results / errors to JS ────────────────────────────────
    def _send_results(self, ranked, stats):
        payload = json.dumps({
            "status": "ok",
            "ranked": ranked,
            "count":  len(ranked),
            "stats":  stats,
        })
        if self.window:
            # Double-encode: json.dumps(payload) makes it a JS string literal
            # so app.js receives a string it can correctly JSON.parse()
            self.window.evaluate_js(f"window.onResults({json.dumps(payload)});")

    def _send_error(self, message):
        payload = json.dumps({"status": "error", "message": message})
        if self.window:
            self.window.evaluate_js(f"window.onResults({json.dumps(payload)});")


# Only run the app when this file is executed directly.
# This guard also prevents worker processes from accidentally
# opening extra windows when running on Windows/macOS.
if __name__ == "__main__":
    api    = API()
    window = webview.create_window(
        "CandidateRanker ", "index.html",
        js_api=api,
        width=1280, height=820, min_size=(900, 600),
    )
    api.set_window(window)

    # webview.start() must run on the main thread (PyWebView requirement).
    # All heavy work (ranking, file loading) runs on background daemon threads inside the API.
    webview.start()