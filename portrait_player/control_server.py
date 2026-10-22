"""Small HTTP control panel that runs alongside the player."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from queue import Empty, SimpleQueue
import re
import threading
from urllib.parse import parse_qs, urlparse

WEB_DIR = Path(__file__).parent / "web"
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".mkv", ".avi", ".webm"}


class MainThread:
    """Runs callables on the Tk thread; VLC and serial are not thread-safe."""

    def __init__(self):
        self._queue = SimpleQueue()

    def call(self, fn, timeout=5.0):
        done = threading.Event()
        box = {}
        self._queue.put((fn, box, done))
        if not done.wait(timeout):
            raise TimeoutError("player is busy")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def drain(self):
        while True:
            try:
                fn, box, done = self._queue.get_nowait()
            except Empty:
                return
            try:
                box["value"] = fn()
            except Exception as exc:  # re-raised in the requesting thread
                box["error"] = exc
            done.set()


class ControlServer:
    def __init__(self, host, port, player, notifier, telemetry, main_thread, upload_dir):
        self.player = player
        self.notifier = notifier
        self.telemetry = telemetry
        self.main = main_thread
        self.upload_dir = Path(upload_dir)
        server = self
        self._httpd = ThreadingHTTPServer((host, port), type("Handler", (_Handler,), {"app": server}))
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="control-server")

    def start(self):
        self._thread.start()

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()

    # --- operations (all run on the Tk thread) -----------------------------

    def state(self):
        data = self.player.state()
        data["telemetry"] = self.telemetry.snapshot()
        data["serial"] = self.notifier.status()
        return data

    def save_upload(self, name, stream, length):
        name = Path(name.replace("\\", "/")).name
        stem, ext = Path(name).stem or "video", Path(name).suffix.lower()
        if ext not in VIDEO_EXTENSIONS:
            raise ValueError("formato não suportado: " + (ext or "sem extensão"))
        stem = re.sub(r"[^\w.\- ]", "_", stem)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        target = self.upload_dir / (stem + ext)
        n = 1
        while target.exists():
            target = self.upload_dir / f"{stem}-{n}{ext}"
            n += 1
        part = target.with_name(target.name + ".part")
        try:
            with open(part, "wb") as out:
                remaining = length
                while remaining > 0:
                    chunk = stream.read(min(1 << 20, remaining))
                    if not chunk:
                        raise ValueError("upload interrompido")
                    out.write(chunk)
                    remaining -= len(chunk)
            part.replace(target)
        finally:
            if part.exists():
                part.unlink()
        return target


class _Handler(BaseHTTPRequestHandler):
    app: ControlServer

    def log_message(self, fmt, *args):
        pass

    def _send(self, status, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length) or b"{}")

    def _same_origin(self):
        origin = self.headers.get("Origin")
        return origin is None or urlparse(origin).netloc == self.headers.get("Host")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, (WEB_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/state":
            self._run(None)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        self._mutate("POST")

    def do_DELETE(self):
        self._mutate("DELETE")

    def _mutate(self, method):
        if not self._same_origin():
            self._send(403, {"error": "origin not allowed"})
            return
        url = urlparse(self.path)
        path = url.path
        app, player = self.app, self.app.player
        try:
            if method == "POST" and path == "/api/playlist/upload":
                name = parse_qs(url.query).get("name", [""])[0]
                target = app.save_upload(name, self.rfile, int(self.headers.get("Content-Length") or 0))
                self._run(lambda: player.add(target))
                return
            body = self._json_body()
            match = re.fullmatch(r"/api/playlist/(\d+)(?:/(rgb))?", path)
            if method == "POST" and path == "/api/next":
                fn = player.next
            elif method == "POST" and path == "/api/previous":
                fn = player.previous
            elif method == "POST" and path == "/api/pause":
                fn = player.pause_resume
            elif method == "POST" and path == "/api/play":
                fn = lambda: player.play_index(body.get("index"))
            elif method == "POST" and path == "/api/playlist/add":
                video = Path(str(body.get("path", "")).strip().strip('"'))
                if video.suffix.lower() not in VIDEO_EXTENSIONS or not video.is_file():
                    raise ValueError("arquivo de vídeo não encontrado")
                fn = lambda: player.add(video.resolve(), body.get("rgb"))
            elif method == "POST" and path == "/api/playlist/move":
                fn = lambda: player.move(body.get("from"), body.get("to"))
            elif method == "POST" and match and match.group(2) == "rgb":
                fn = lambda: player.set_rgb(int(match.group(1)), body.get("rgb"))
            elif method == "DELETE" and match and not match.group(2):
                fn = lambda: player.remove(int(match.group(1)))
            elif method == "POST" and path == "/api/led":
                fn = lambda: player.set_led_mode(body.get("enabled"))
            elif method == "POST" and path == "/api/led/rgb":
                fn = lambda: player.send_led(body.get("rgb"))
            else:
                self._send(404, {"error": "not found"})
                return
        except (ValueError, TypeError) as exc:
            self._send(400, {"error": str(exc)})
            return
        self._run(fn)

    def _run(self, fn):
        try:
            if fn is not None:
                self.app.main.call(fn)
            self._send(200, self.app.main.call(self.app.state))
        except TimeoutError as exc:
            self._send(503, {"error": str(exc)})
        except (ValueError, TypeError) as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})
