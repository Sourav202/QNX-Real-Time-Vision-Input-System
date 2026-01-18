from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import time
import urllib.parse
import subprocess

SAVE_DIR = "incoming"
os.makedirs(SAVE_DIR, exist_ok=True)

# One-slot command mailbox
NEXT_CMD = "NOOP"


def _save_bytes_as_mp4(data: bytes) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    fname = f"clip_{ts}.mp4"
    out_path = os.path.join(SAVE_DIR, fname)
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path


def run_finger_counter_stream(video_path: str) -> str:
    """
    Runs finger_counter.py using Python 3.10 (MediaPipe).
    Streams ALL output from finger_counter into this server console live.
    Returns the LAST non-empty line printed by finger_counter (should be: 0-5 or UNKNOWN).
    """
    cmd = ["py", "-3.10", "finger_counter.py", video_path]
    print(f"[vision] running: {' '.join(cmd)}")

    try:
        p = subprocess.Popen(
            cmd,
            cwd=os.getcwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # line-buffered
            universal_newlines=True,
        )

        last_nonempty = None

        # Stream output live
        assert p.stdout is not None
        for line in p.stdout:
            line = line.rstrip("\r\n")
            if line:
                last_nonempty = line
            print(f"[vision] {line}")

        rc = p.wait(timeout=60)
        if rc != 0:
            return f"ERROR: finger_counter exit={rc}"

        if last_nonempty is None:
            return "ERROR: no output from finger_counter"

        # last_nonempty should be the final answer line from finger_counter.py
        return last_nonempty

    except subprocess.TimeoutExpired:
        try:
            p.kill()
        except Exception:
            pass
        return "ERROR: finger_counter timeout"
    except FileNotFoundError:
        return "ERROR: 'py' launcher not found (is Python Launcher installed?)"
    except Exception as e:
        return f"ERROR: {e}"


class Handler(BaseHTTPRequestHandler):
    # quiet default access logs
    def log_message(self, fmt, *args):
        pass

    def _send_text(self, code: int, text: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write((text + "\n").encode("utf-8"))

    def do_GET(self):
        global NEXT_CMD

        # QNX polls here; consume the command
        if self.path.startswith("/next_cmd"):
            cmd = NEXT_CMD
            NEXT_CMD = "NOOP"
            self._send_text(200, cmd)
            if cmd != "NOOP":
                print(f"[cmd] served: {cmd}")
            return

        # /set_cmd?cmd=RECORD%205%20expected%3D3
        if self.path.startswith("/set_cmd"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            cmd = params.get("cmd", ["NOOP"])[0]
            NEXT_CMD = cmd
            self._send_text(200, "OK")
            print(f"[cmd] set: {cmd}")
            return

        # Easy trigger: /trigger?seconds=5&expected=3
        if self.path.startswith("/trigger"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            seconds = params.get("seconds", ["5"])[0]
            expected = params.get("expected", ["3"])[0]
            cmd = f"RECORD {seconds} expected={expected}"
            NEXT_CMD = cmd
            self._send_text(200, "OK")
            print(f"[cmd] set: {cmd}")
            return

        # health
        if self.path == "/" or self.path.startswith("/health"):
            self._send_text(200, "OK")
            return

        self._send_text(404, "Not Found")

    # Optional raw POST upload
    def do_POST(self):
        if self.path != "/upload":
            self._send_text(404, "Not Found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)

        out_path = _save_bytes_as_mp4(body)
        print(f"[upload] POST saved {out_path} ({len(body)} bytes)")

        # Run classifier and return result to client
        result = run_finger_counter_stream(out_path)
        print(f"[vision] FINAL → {result}")
        self._send_text(200, result)

    # ✅ QNX uses: curl -T file http://PC:8000/upload  (HTTP PUT)
    def do_PUT(self):
        if self.path != "/upload":
            self._send_text(404, "Not Found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)

        out_path = _save_bytes_as_mp4(body)
        print(f"[upload] PUT saved {out_path} ({len(body)} bytes)")

        # Run classifier and return result to client
        result = run_finger_counter_stream(out_path)
        print(f"[vision] FINAL → {result}")
        self._send_text(200, result)


def main():
    host = "0.0.0.0"
    port = 8000
    print(f"Server on http://{host}:{port}")
    print("QNX polls:        GET  /next_cmd")
    print("Set command:      GET  /set_cmd?cmd=RECORD%205%20expected%3D3")
    print("Easy trigger:     GET  /trigger?seconds=5&expected=3")
    print("Upload (PUT):     PUT  /upload   (QNX: curl -T file http://PC:8000/upload)")
    print("Upload (POST):    POST /upload   (raw body)")
    print("Vision:           runs finger_counter.py via: py -3.10 finger_counter.py <saved_mp4>")
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
