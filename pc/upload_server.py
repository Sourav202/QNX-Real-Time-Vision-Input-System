from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import time
import urllib.parse

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
        self._send_text(200, out_path)
        print(f"[upload] POST saved {out_path} ({len(body)} bytes)")

    # ✅ QNX uses: curl -T file http://PC:8000/upload  (HTTP PUT)
    def do_PUT(self):
        if self.path != "/upload":
            self._send_text(404, "Not Found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)

        out_path = _save_bytes_as_mp4(body)
        self._send_text(200, out_path)
        print(f"[upload] PUT saved {out_path} ({len(body)} bytes)")


def main():
    host = "0.0.0.0"
    port = 8000
    print(f"Server on http://{host}:{port}")
    print("QNX polls:        GET  /next_cmd")
    print("Set command:      GET  /set_cmd?cmd=RECORD%205%20expected%3D3")
    print("Easy trigger:     GET  /trigger?seconds=5&expected=3")
    print("Upload (PUT):     PUT  /upload   (QNX: curl -T file http://PC:8000/upload)")
    print("Upload (POST):    POST /upload   (raw body)")
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
