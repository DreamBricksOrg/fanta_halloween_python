import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from portrait_player.control_server import ControlServer, MainThread
from portrait_player.playback import PlaylistPlayer
from portrait_player.serial_signal import SerialNotifier
from portrait_player.telemetry import Telemetry


class Backend:
    def play(self, path, on_started):
        on_started()

    def pause(self):
        pass

    def set_pause(self, paused):
        pass

    def stop(self):
        pass


class FakeSerial:
    def __init__(self):
        self.writes = []

    def write(self, payload):
        self.writes.append(payload)


@pytest.fixture
def server(tmp_path):
    telemetry = Telemetry()
    serial = FakeSerial()
    notifier = SerialNotifier(serial, telemetry)
    player = PlaylistPlayer([tmp_path / "a.mp4", tmp_path / "b.mp4"], Backend(), notifier, on_event=telemetry.event)
    main = MainThread()
    srv = ControlServer("127.0.0.1", 0, player, notifier, telemetry, main, tmp_path / "videos")
    srv.start()
    stop = threading.Event()

    def pump():
        while not stop.is_set():
            main.drain()
            stop.wait(0.005)

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    player.start()
    srv.serial = serial
    srv.url = f"http://127.0.0.1:{srv.port}"
    yield srv
    stop.set()
    srv.stop()


def call(server, method, path, body=None, raw=None, headers=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = Request(server.url + path, data=data, method=method, headers=headers or {})
    try:
        with urlopen(req) as res:
            return res.status, json.loads(res.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_state_includes_playlist_and_telemetry(server):
    status, data = call(server, "GET", "/api/state")
    assert status == 200
    assert [v["name"] for v in data["playlist"]] == ["a.mp4", "b.mp4"]
    assert data["telemetry"]["uptime_s"] >= 0
    assert data["serial"]["connected"] is True
    assert data["telemetry"]["counters"]["serial_tx"] == 1  # the first video start was logged


def test_led_mode_sends_rgb_over_serial(server):
    status, data = call(server, "POST", "/api/led/rgb", {"rgb": [1, 2, 3]})
    assert status == 200 and data["led_mode"] is True
    assert server.serial.writes[-1] == b"RGB(1,2,3)\n"
    status, data = call(server, "POST", "/api/led", {"enabled": False})
    assert data["led_mode"] is False


def test_invalid_rgb_is_rejected(server):
    status, data = call(server, "POST", "/api/led/rgb", {"rgb": [1, 2, 999]})
    assert status == 400 and "RGB" in data["error"]


def test_move_delete_and_color_endpoints(server):
    status, data = call(server, "POST", "/api/playlist/move", {"from": 1, "to": 0})
    assert [v["name"] for v in data["playlist"]] == ["b.mp4", "a.mp4"]
    status, data = call(server, "POST", "/api/playlist/0/rgb", {"rgb": [5, 6, 7]})
    assert data["playlist"][0]["rgb"] == [5, 6, 7]
    status, data = call(server, "DELETE", "/api/playlist/1")
    assert len(data["playlist"]) == 1
    status, data = call(server, "DELETE", "/api/playlist/0")
    assert status == 400


def test_upload_adds_video_without_overwriting_existing_file(server):
    for expected in ("clip.mp4", "clip-1.mp4"):
        status, data = call(server, "POST", "/api/playlist/upload?name=..%5Cclip.mp4", raw=b"data")
        assert status == 200 and data["playlist"][-1]["name"] == expected
    status, data = call(server, "POST", "/api/playlist/upload?name=notes.txt", raw=b"x")
    assert status == 400


def test_cross_origin_writes_are_refused(server):
    status, _ = call(server, "POST", "/api/next", {}, headers={"Origin": "http://evil.example"})
    assert status == 403


def test_serves_control_page(server):
    with urlopen(server.url + "/") as res:
        assert b"Telemetria" in res.read()


def test_events_persist_per_day_and_survive_restart(tmp_path):
    from datetime import date

    telemetry = Telemetry(log_dir=tmp_path)
    telemetry.event("video", "#0 a.mp4 iniciou")
    telemetry.event("serial_tx", "RGB(1,2,3)", ok=False)
    today = date.today().isoformat()
    assert telemetry.log_days() == [today]
    assert [e["text"] for e in telemetry.day_events(today)] == ["#0 a.mp4 iniciou", "RGB(1,2,3)"]
    assert telemetry.day_events("../secrets") == []

    restarted = Telemetry(log_dir=tmp_path)
    assert len(restarted.snapshot()["events"]) == 2
