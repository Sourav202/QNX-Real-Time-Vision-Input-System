from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import time
import urllib.parse
import subprocess
import json
from urllib.parse import urlparse, parse_qs, unquote


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# UI files live here: pc/ui/index.html, pc/ui/app.js, pc/ui/styles.css
UI_DIR = os.path.join(BASE_DIR, "ui")

# IMPORTANT: incoming is one directory higher than /pc
SAVE_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "incoming"))
os.makedirs(SAVE_DIR, exist_ok=True)

# One-slot command mailbox
NEXT_CMD = "NOOP"

# Last-seen info (useful for UI/polling)
LAST_UPLOAD_NAME = None
LAST_UPLOAD_TS = None
LAST_RESULT = None


def _read_file_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _guess_content_type(path: str) -> str:
    low = path.lower()
    if low.endswith(".html"):
        return "text/html; charset=utf-8"
    if low.endswith(".css"):
        return "text/css; charset=utf-8"
    if low.endswith(".js"):
        return "application/javascript; charset=utf-8"
    if low.endswith(".json"):
        return "application/json; charset=utf-8"
    if low.endswith(".mp4"):
        return "video/mp4"
    return "application/octet-stream"


def _save_bytes_as_mp4(data: bytes) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    fname = f"clip_{ts}.mp4"
    out_path = os.path.join(SAVE_DIR, fname)
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path


def list_mp4s():
    clips = []
    try:
        names = os.listdir(SAVE_DIR)
    except OSError:
        names = []
    for name in names:
        if not name.lower().endswith(".mp4"):
            continue
        p = os.path.join(SAVE_DIR, name)
        try:
            st = os.stat(p)
            clips.append(
                {
                    "name": name,
                    "size_bytes": st.st_size,
                    "mtime_ms": int(st.st_mtime * 1000),
                }
            )
        except OSError:
            pass
    clips.sort(key=lambda x: x["mtime_ms"], reverse=True)
    return clips


def run_finger_counter_stream(video_path: str) -> str:
    """
    Runs finger_counter.py using Python 3.10 (MediaPipe).
    Streams ALL output from finger_counter into this server console live.
    Returns the LAST non-empty line printed by finger_counter (should be: 0-5 or UNKNOWN).
    """
    finger_py = os.path.join(BASE_DIR, "finger_counter.py")
    cmd = ["py", "-3.10", finger_py, video_path]
    print(f"[vision] running: {' '.join(cmd)}")

    try:
        p = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        last_nonempty = None
        assert p.stdout is not None

        for line in p.stdout:
            line = line.rstrip("\r\n")
            if line:
                last_nonempty = line
            print(f"[vision] {line}")

        rc = p.wait(timeout=120)
        if rc != 0:
            return f"ERROR: finger_counter exit={rc}"

        if last_nonempty is None:
            return "ERROR: no output from finger_counter"

        return last_nonempty

    except subprocess.TimeoutExpired:
        try:
            p.kill()
        except Exception:
            pass
        return "ERROR: finger_counter timeout"
    except FileNotFoundError:
        return "ERROR: 'py' launcher not found (install Python Launcher)"
    except Exception as e:
        return f"ERROR: {e}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # quiet default access logs
        pass

    def _send_text(self, code: int, text: str):
        data = (text + "\n").encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, code: int, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: str, content_type: str | None = None):
        if not os.path.isfile(path):
            self.send_error(404)
            return
        data = _read_file_bytes(path)
        ct = content_type or _guess_content_type(path)
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _stream_file(self, path: str, content_type: str):
        """Stream big files (mp4) in chunks."""
        if not os.path.isfile(path):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(os.path.getsize(path)))
        self.end_headers()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def do_GET(self):
        global NEXT_CMD, LAST_UPLOAD_NAME, LAST_UPLOAD_TS, LAST_RESULT

        parsed = urlparse(self.path)
        path = parsed.path  # IMPORTANT: ignore query string

        # ---------------------------
        # UI routes (serve pc/ui/*)
        # ---------------------------
        if path == "/" or path == "/index.html":
            f = os.path.join(UI_DIR, "index.html")
            if not os.path.isfile(f):
                return self._send_text(404, f"UI missing: {f}")
            return self._send_file(f, "text/html; charset=utf-8")

        if path == "/app.js":
            f = os.path.join(UI_DIR, "app.js")
            if not os.path.isfile(f):
                return self._send_text(404, f"UI missing: {f}")
            return self._send_file(f, "application/javascript; charset=utf-8")

        if path == "/styles.css":
            f = os.path.join(UI_DIR, "styles.css")
            if not os.path.isfile(f):
                return self._send_text(404, f"UI missing: {f}")
            return self._send_file(f, "text/css; charset=utf-8")

        # ---------------------------
        # Serve uploaded mp4s
        # ---------------------------
        if path.startswith("/incoming/"):
            name = unquote(path[len("/incoming/"):])
            safe = os.path.basename(name)
            fpath = os.path.join(SAVE_DIR, safe)
            return self._stream_file(fpath, "video/mp4")

        # ---------------------------
        # API endpoints (for UI)
        # ---------------------------
        if path == "/api/status":
            return self._send_json(200, {
                "last_upload_name": LAST_UPLOAD_NAME,
                "last_upload_ts": LAST_UPLOAD_TS,
                "last_result": LAST_RESULT,
            })

        if path == "/api/clips":
            return self._send_json(200, list_mp4s())

        if path == "/api/info":
            return self._send_json(200, {
                "server": "upload_server.py",
                "save_dir": SAVE_DIR,
                "ui_dir": UI_DIR,
            })

        # ---------------------------
        # QNX command endpoints
        # ---------------------------
        if path == "/next_cmd":
            cmd = NEXT_CMD
            NEXT_CMD = "NOOP"
            return self._send_text(200, cmd)

        if path == "/set_cmd":
            params = urllib.parse.parse_qs(parsed.query)
            cmd = params.get("cmd", ["NOOP"])[0]
            NEXT_CMD = cmd
            return self._send_text(200, "OK")

        if path == "/trigger":
            params = urllib.parse.parse_qs(parsed.query)
            seconds = params.get("seconds", ["5"])[0]
            expected = params.get("expected", ["3"])[0]
            cmd = f"RECORD {seconds} expected={expected}"
            NEXT_CMD = cmd
            if params.get("json", ["0"])[0] == "1":
                return self._send_json(200, {"ok": True, "command": cmd})
            return self._send_text(200, "OK")

        if path.startswith("/health"):
            return self._send_text(200, "OK")

        return self._send_text(404, "Not Found")

    def do_POST(self):
        # Optional raw POST upload support
        return self._handle_upload()

    def do_PUT(self):
        # ✅ QNX uses: curl -T file http://PC:8000/upload  (HTTP PUT)
        return self._handle_upload()

    def _handle_upload(self):
        global LAST_UPLOAD_NAME, LAST_UPLOAD_TS, LAST_RESULT

        if self.path != "/upload":
            return self._send_text(404, "Not Found")

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)

        out_path = _save_bytes_as_mp4(body)
        LAST_UPLOAD_NAME = os.path.basename(out_path)
        LAST_UPLOAD_TS = time.time()

        print(f"[upload] saved {out_path} ({len(body)} bytes)")

        # Run classifier and return result to client
        result = run_finger_counter_stream(out_path)
        LAST_RESULT = result

        print(f"[vision] FINAL → {result}")
        return self._send_text(200, result)


def main():
    host = "0.0.0.0"
    port = 8000

    print(f"Server:  http://{host}:{port}")
    print("UI:      http://localhost:8000/")
    print()
    print("QNX polls:        GET  /next_cmd")
    print("Set command:      GET  /set_cmd?cmd=RECORD%205%20expected%3D3")
    print("Easy trigger:     GET  /trigger?seconds=5&expected=3")
    print("Upload (PUT):     PUT  /upload   (QNX: curl -T file http://PC:8000/upload)")
    print()
    print(f"Save dir: {SAVE_DIR}")
    print(f"UI dir:   {UI_DIR}")
    print("Vision:   runs finger_counter.py via: py -3.10 finger_counter.py <saved_mp4>")
    print()

    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
