"""Integrated Real-Time NASA Astronaut Health Monitoring Server & Dashboard.

Runs the live video capture + LibreFace feature extraction + alerting node +
serves an interactive web dashboard with embedded live MJPEG video feed and
Server-Sent Events (SSE) telemetry.
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from alerting.adapters.facial import get_facial_config
from alerting.core.node import AlertNode
from facial.extractor import LibreFaceExtractor
from facial.windows import WindowAggregator


class VideoStreamHub:
    """Thread-safe frame buffer holding the latest annotated video frame as JPEG."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.latest_jpeg: Optional[bytes] = None
        self.latest_alert: Dict[str, Any] = {
            "state": "calibrating",
            "score": 0.0,
            "quality": 1.0,
            "drift": {"percentile": None, "enabled": True},
            "contributors": [],
            "reason": "Initializing pipeline...",
            "t": "",
        }

    def set_frame(self, frame_bgr: np.ndarray, alert_data: Dict[str, Any]) -> None:
        # Overlay visual state banner on frame
        state = alert_data.get("state", "normal")
        score = alert_data.get("score", 0.0)

        color_map = {
            "calibrating": (248, 189, 56),  # cyan
            "normal": (34, 197, 94),        # green
            "watch": (8, 179, 234),         # yellow
            "alert": (68, 68, 239),         # red
            "invalid": (181, 157, 142),     # gray
        }
        bgr_color = color_map.get(state, (255, 255, 255))

        annotated = frame_bgr.copy()
        h, w = annotated.shape[:2]

        # Header bar
        cv2.rectangle(annotated, (0, 0), (w, 42), (15, 23, 42), -1)
        status_text = f"[{state.upper()}] SCORE: {score:.2f}"
        cv2.putText(
            annotated, status_text, (15, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, bgr_color, 2
        )

        # Border outline when alerting or watching
        if state in ("alert", "watch"):
            cv2.rectangle(annotated, (0, 0), (w - 1, h - 1), bgr_color, 4)

        # Encode JPEG
        ret, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ret:
            with self.lock:
                self.latest_jpeg = jpeg.tobytes()
                self.latest_alert = alert_data

    def get_jpeg(self) -> Optional[bytes]:
        with self.lock:
            return self.latest_jpeg

    def get_alert(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.latest_alert)


HUB = VideoStreamHub()


HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Astronaut Health Monitor | Mission Control</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: #141c2e;
      --border: #23314d;
      --text: #e2e8f0;
      --text-muted: #8e9db5;
      --cyan: #38bdf8;
      --green: #22c55e;
      --yellow: #eab308;
      --red: #ef4444;
      --blue: #3b82f6;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 20px; line-height: 1.5; }
    header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 16px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
    .title-group { display: flex; align-items: center; gap: 12px; }
    .badge-live { display: inline-flex; align-items: center; gap: 6px; background: rgba(34, 197, 94, 0.15); color: var(--green); padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; border: 1px solid rgba(34, 197, 94, 0.3); }
    .pulse-dot { width: 8px; height: 8px; background: var(--green); border-radius: 50%; animation: pulse 1.5s infinite; }
    @keyframes pulse { 0% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.8); } 100% { opacity: 1; transform: scale(1); } }
    
    .grid-main { display: grid; grid-template-columns: 1fr 380px; gap: 20px; margin-bottom: 20px; }
    @media (max-width: 1024px) { .grid-main { grid-template-columns: 1fr; } }
    
    .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
    .card-title { font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); margin-bottom: 16px; display: flex; justify-content: space-between; }
    
    /* Video Box */
    .video-container { position: relative; width: 100%; border-radius: 8px; overflow: hidden; background: #000; aspect-ratio: 16/9; display: flex; align-items: center; justify-content: center; }
    .video-stream { width: 100%; height: 100%; object-fit: contain; }

    /* State Pill */
    .state-box { text-align: center; padding: 20px 16px; border-radius: 10px; margin-bottom: 20px; transition: all 0.3s; }
    .state-label { font-size: 12px; letter-spacing: 0.1em; text-transform: uppercase; opacity: 0.8; margin-bottom: 2px; }
    .state-value { font-size: 28px; font-weight: 800; letter-spacing: 0.05em; text-transform: uppercase; }
    
    .state-calibrating { background: rgba(56, 189, 248, 0.12); color: var(--cyan); border: 1px solid rgba(56, 189, 248, 0.3); }
    .state-normal { background: rgba(34, 197, 94, 0.12); color: var(--green); border: 1px solid rgba(34, 197, 94, 0.3); }
    .state-watch { background: rgba(234, 179, 8, 0.12); color: var(--yellow); border: 1px solid rgba(234, 179, 8, 0.3); }
    .state-alert { background: rgba(239, 68, 68, 0.15); color: var(--red); border: 1px solid rgba(239, 68, 68, 0.4); animation: alertPulse 2s infinite; }
    .state-invalid { background: rgba(142, 157, 181, 0.1); color: var(--text-muted); border: 1px solid var(--border); }
    @keyframes alertPulse { 0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); } 70% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); } 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); } }

    /* Metric bars */
    .metric-row { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; font-size: 13px; }
    .metric-value { font-weight: 700; font-family: monospace; font-size: 15px; }
    .meter-bar { width: 100%; height: 7px; background: rgba(255,255,255,0.06); border-radius: 999px; overflow: hidden; margin-bottom: 14px; }
    .meter-fill { height: 100%; width: 0%; transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1), background-color 0.4s; }

    /* Reason box */
    .reason-box { background: rgba(0,0,0,0.3); border-left: 3px solid var(--cyan); padding: 12px 14px; border-radius: 6px; font-size: 13px; color: #cbd5e1; margin-top: 14px; min-height: 44px; }

    /* Contributors Table */
    .contrib-list { display: flex; flex-direction: column; gap: 8px; margin-top: 16px; }
    .contrib-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; background: rgba(255,255,255,0.02); border-radius: 6px; border: 1px solid rgba(255,255,255,0.04); }
    .contrib-name { font-weight: 600; font-size: 13px; }
    .contrib-stats { font-family: monospace; font-size: 12px; color: var(--text-muted); }
    .dir-pill { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; margin-left: 6px; }
    .dir-up { background: rgba(239, 68, 68, 0.2); color: var(--red); }
    .dir-down { background: rgba(56, 189, 248, 0.2); color: var(--cyan); }

    /* Timeline */
    .timeline { max-height: 180px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
    .timeline-row { display: flex; justify-content: space-between; font-size: 12px; padding: 6px 10px; background: rgba(0,0,0,0.25); border-radius: 6px; }
  </style>
</head>
<body>
  <header>
    <div class="title-group">
      <h1 style="font-size: 18px; font-weight: 700;">NASA Space Apps | Astronaut Self-Monitoring</h1>
      <span class="badge-live"><span class="pulse-dot"></span> Live Feed</span>
    </div>
    <div style="font-size: 13px; color: var(--text-muted);" id="last-update">Connecting...</div>
  </header>

  <div class="grid-main">
    <!-- Left: Video Stream & Timeline -->
    <div style="display: flex; flex-direction: column; gap: 20px;">
      <div class="card" style="padding: 16px;">
        <div class="card-title">
          <span>Camera Stream & Landmark Tracking</span>
          <span style="font-size: 11px; text-transform: none; color: var(--green);">● Active Capture</span>
        </div>
        <div class="video-container">
          <img src="/video_feed" class="video-stream" alt="Live Camera Feed">
        </div>
      </div>

      <div class="card">
        <div class="card-title">Contributing Feature Deviations (Top Flags)</div>
        <div id="contributors" class="contrib-list">
          <div style="color: var(--text-muted); font-size: 13px;">No abnormal deviations flagged.</div>
        </div>
      </div>
    </div>

    <!-- Right: Health Telemetry & Gauges -->
    <div style="display: flex; flex-direction: column; gap: 20px;">
      <div class="card">
        <div class="card-title">Astronaut Health Assessment</div>
        <div id="state-box" class="state-box state-calibrating">
          <div class="state-label">State</div>
          <div id="state-val" class="state-value">CALIBRATING</div>
        </div>

        <div class="metric-row">
          <span>Severity Anomaly Score</span>
          <span id="score-val" class="metric-value">0.00</span>
        </div>
        <div class="meter-bar">
          <div id="score-fill" class="meter-fill" style="background: var(--cyan);"></div>
        </div>

        <div class="metric-row">
          <span>Manifold Drift Percentile</span>
          <span id="drift-val" class="metric-value">-- %</span>
        </div>
        <div class="meter-bar">
          <div id="drift-fill" class="meter-fill" style="background: var(--blue);"></div>
        </div>

        <div class="metric-row">
          <span>Signal Quality</span>
          <span id="quality-val" class="metric-value">1.00</span>
        </div>
        <div class="meter-bar">
          <div id="quality-fill" class="meter-fill" style="background: var(--green); width: 100%;"></div>
        </div>

        <div class="card-title" style="margin-top: 20px;">Explainable Clinical Reason</div>
        <div id="reason-text" class="reason-box">Calibrating astronaut baseline...</div>
      </div>

      <div class="card">
        <div class="card-title">Alert Event Log</div>
        <div id="timeline" class="timeline"></div>
      </div>
    </div>
  </div>

  <script>
    const evtSource = new EventSource("/stream");
    const timelineEl = document.getElementById("timeline");

    evtSource.onmessage = function(event) {
      const data = JSON.parse(event.data);
      if (!data) return;

      document.getElementById("last-update").textContent = "Updated: " + new Date().toLocaleTimeString();

      // State pill
      const state = data.state || "normal";
      const stateBox = document.getElementById("state-box");
      const stateVal = document.getElementById("state-val");
      stateBox.className = "state-box state-" + state;
      stateVal.textContent = state.toUpperCase();

      // Score
      const score = Math.min(1.0, Math.max(0.0, data.score || 0));
      document.getElementById("score-val").textContent = score.toFixed(2);
      const scoreFill = document.getElementById("score-fill");
      scoreFill.style.width = (score * 100) + "%";
      if (score >= 0.7) scoreFill.style.backgroundColor = "var(--red)";
      else if (score >= 0.4) scoreFill.style.backgroundColor = "var(--yellow)";
      else scoreFill.style.backgroundColor = "var(--cyan)";

      // Drift
      const driftVal = document.getElementById("drift-val");
      const driftFill = document.getElementById("drift-fill");
      if (data.drift && data.drift.percentile !== null && data.drift.enabled) {
        driftVal.textContent = data.drift.percentile.toFixed(1) + "%";
        driftFill.style.width = data.drift.percentile + "%";
      } else {
        driftVal.textContent = "N/A";
        driftFill.style.width = "0%";
      }

      // Quality
      const qual = Math.min(1.0, Math.max(0.0, data.quality !== undefined ? data.quality : 1.0));
      document.getElementById("quality-val").textContent = qual.toFixed(2);
      document.getElementById("quality-fill").style.width = (qual * 100) + "%";

      // Reason
      document.getElementById("reason-text").textContent = data.reason || "Metrics within baseline range.";

      // Contributors
      const contribEl = document.getElementById("contributors");
      if (data.contributors && data.contributors.length > 0) {
        contribEl.innerHTML = data.contributors.map(c => `
          <div class="contrib-item">
            <div>
              <span class="contrib-name">${c.feature}</span>
              <span class="dir-pill dir-${c.direction}">${c.direction.toUpperCase()}</span>
            </div>
            <div class="contrib-stats">
              z = ${c.z > 0 ? "+" : ""}${c.z.toFixed(2)} | CUSUM: ${c.cusum.toFixed(1)} | ${c.windows_flagged}w
            </div>
          </div>
        `).join("");
      } else {
        contribEl.innerHTML = `<div style="color: var(--text-muted); font-size: 13px;">No abnormal deviations flagged.</div>`;
      }

      // Timeline append
      const row = document.createElement("div");
      row.className = "timeline-row";
      const timeStr = new Date().toLocaleTimeString();
      row.innerHTML = `
        <span style="color: var(--text-muted);">${timeStr}</span>
        <span style="font-weight: 700; text-transform: uppercase;">${state}</span>
        <span>score: ${score.toFixed(2)}</span>
      `;
      timelineEl.insertBefore(row, timelineEl.firstChild);
      if (timelineEl.children.length > 25) timelineEl.removeChild(timelineEl.lastChild);
    };
  </script>
</body>
</html>
"""


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    """Serves the dashboard HTML, MJPEG video stream, and SSE events."""

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_DASHBOARD.encode("utf-8"))

        elif self.path == "/video_feed":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    jpeg = HUB.get_jpeg()
                    if jpeg is not None:
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                    time.sleep(0.04)  # ~25 FPS stream
            except (BrokenPipeError, ConnectionResetError):
                pass

        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            last_sent = None
            try:
                while True:
                    alert = HUB.get_alert()
                    t_val = alert.get("t")
                    if t_val != last_sent:
                        payload = json.dumps(alert)
                        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        last_sent = t_val
                    time.sleep(0.2)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_response(404)
            self.end_headers()


def run_pipeline(
    source: str = "0",
    window_sec: float = 5.0,
    fps: float = 15.0,
    device: str = "auto",
    subject_id: str = "Astronaut",
    state_file: str = ".alert_state_facial.json",
    port: int = 8080,
) -> None:
    """Run camera capture, feature extraction, alerting, and HTTP dashboard in one process."""
    cap_source: Any = int(source) if source.isdigit() else source
    cap = cv2.VideoCapture(cap_source)
    if not cap.isOpened():
        print(f"Error: Could not open source '{source}'", file=sys.stderr)
        return

    # Device auto-detect
    if device == "auto":
        import torch
        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

    print(f"Loading LibreFace extractor on device='{device}'...")
    extractor = LibreFaceExtractor(device=device)
    print("Extractor initialized.")

    config = get_facial_config()
    if os.path.exists(state_file):
        print(f"Resuming alert baseline from '{state_file}'...")
        node = AlertNode.load_state(state_file)
    else:
        print("Starting fresh calibration...")
        node = AlertNode(config=config, subject_id=subject_id)

    frames_per_window = max(1, int(round(window_sec * fps)))
    aggregator = WindowAggregator(window_size=frames_per_window)

    # Start HTTP dashboard server
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), DashboardHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"\n==============================================================")
    print(f" LIVE ASTRONAUT MONITOR READY AT: http://localhost:{port}")
    print(f"==============================================================\n")

    current_alert = {
        "state": node.last_valid_state,
        "score": 0.0,
        "quality": 1.0,
        "drift": {"percentile": None, "enabled": True},
        "contributors": [],
        "reason": "Monitoring active.",
        "t": "",
    }

    frame_interval = 1.0 / fps
    try:
        while True:
            t0 = time.time()
            ret, frame = cap.read()
            if not ret or frame is None:
                # Loop video if pre-recorded file
                if not isinstance(cap_source, int):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    break

            # Extract features
            frame_data = extractor.extract_frame(frame)
            window_record = aggregator.add_frame(frame_data)

            if window_record is not None:
                current_alert = node.process_record(window_record)
                node.save_state(state_file)

            # Update live video hub with annotated frame
            HUB.set_frame(frame, current_alert)

            # Throttle to target FPS
            duration = time.time() - t0
            sleep_t = frame_interval - duration
            if sleep_t > 0:
                time.sleep(sleep_t)

    except KeyboardInterrupt:
        print("\nStopping monitor...")
    finally:
        cap.release()
        server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-Time Video & Alert Dashboard")
    parser.add_argument("--source", type=str, default="0", help="Webcam index (0) or path to video file")
    parser.add_argument("--fps", type=float, default=15.0, help="Target FPS (default: 15.0)")
    parser.add_argument("--window", type=float, default=5.0, help="Window duration in seconds (default: 5.0)")
    parser.add_argument("--device", type=str, default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument("--port", type=int, default=8080, help="Dashboard port (default: 8080)")
    args = parser.parse_args()

    run_pipeline(
        source=args.source,
        window_sec=args.window,
        fps=args.fps,
        device=args.device,
        port=args.port,
    )
