from pathlib import Path

import pytest

from portrait_player.playback import PlaylistPlayer, parse_cues
from portrait_player.playlist_state import load_state, save_state


class Backend:
    def __init__(self):
        self.time = 0
        self.seeks = []

    def play(self, path, on_started):
        self.time = 0
        on_started()

    def pause(self):
        pass

    def set_pause(self, paused):
        pass

    def stop(self):
        pass

    def get_time(self):
        return self.time

    def get_length(self):
        return 60000

    def set_time(self, ms):
        self.seeks.append(ms)
        self.time = ms


class Notifier:
    def __init__(self):
        self.sent = []

    def playback_started(self, index, rgb):
        self.sent.append(tuple(rgb))

    def send_rgb(self, rgb, source=""):
        self.sent.append(tuple(rgb))

    def close(self):
        pass


RED, GREEN, BLUE = [255, 0, 0], [0, 255, 0], [0, 0, 255]
CUES = [{"t": 10, "rgb": GREEN}, {"t": 0, "rgb": RED}, {"t": 20.5, "rgb": BLUE}]


def make(lead=0, cues=CUES):
    backend, notifier = Backend(), Notifier()
    player = PlaylistPlayer([Path("a.mp4")], backend, notifier, [(1, 1, 1)], video_cues=[parse_cues(cues)], cue_lead_ms=lead)
    player.start()
    return player, backend, notifier


def test_cue_at_zero_is_sent_on_start_and_each_cue_fires_once_at_its_time():
    player, backend, notifier = make()
    assert notifier.sent == [(255, 0, 0)]
    for ms in (0, 5000, 9999):
        backend.time = ms
        player.tick()
    assert notifier.sent == [(255, 0, 0)]
    backend.time = 10000
    player.tick()
    player.tick()
    assert notifier.sent == [(255, 0, 0), (0, 255, 0)]
    backend.time = 20500
    player.tick()
    assert notifier.sent[-1] == (0, 0, 255)


def test_without_cue_at_zero_base_color_is_used_until_first_cue():
    player, backend, notifier = make(cues=[{"t": 3, "rgb": GREEN}])
    assert notifier.sent == [(1, 1, 1)]
    backend.time = 3000
    player.tick()
    assert notifier.sent[-1] == (0, 255, 0)
    backend.time = 100  # looped / sought back before the first cue
    player.tick()
    assert notifier.sent[-1] == (1, 1, 1)


def test_seek_resends_color_for_new_position_and_loop_restarts_cues():
    player, backend, notifier = make()
    player.seek(25)
    assert backend.seeks == [25000]
    player.tick()
    assert notifier.sent[-1] == (0, 0, 255)
    backend.on_end()  # single video loops: back to the first cue
    assert notifier.sent[-1] == (255, 0, 0)


def test_lead_fires_cue_early():
    player, backend, notifier = make(lead=300)
    backend.time = 9700
    player.tick()
    assert notifier.sent[-1] == (0, 255, 0)


def test_set_cues_validates_and_resends_active_color_live():
    player, backend, notifier = make()
    backend.time = 5000
    player.set_cues(0, [{"t": 4, "rgb": BLUE}])
    player.tick()
    assert notifier.sent[-1] == (0, 0, 255)
    with pytest.raises(ValueError):
        player.set_cues(0, [{"t": 1, "rgb": RED}, {"t": 1, "rgb": BLUE}])
    with pytest.raises(ValueError):
        player.set_cues(0, [{"t": -1, "rgb": RED}])
    with pytest.raises(ValueError):
        player.set_cues(0, [{"t": 1, "rgb": [1, 2]}])


def test_state_reports_cues_position_and_length_and_cues_follow_reorder():
    player, backend, _ = make()
    player.add("b.mp4")
    backend.time = 1234
    state = player.state()
    assert state["position_ms"] == 1234 and state["length_ms"] == 60000
    assert [c["t"] for c in state["playlist"][0]["cues"]] == [0, 10, 20.5]
    player.move(0, 1)
    assert player.state()["playlist"][1]["cues"] and not player.state()["playlist"][0]["cues"]


def test_cues_survive_save_and_load(tmp_path):
    player, _, _ = make()
    path = tmp_path / "state.json"
    save_state(path, player)
    videos, rgbs, cues = load_state(path)
    assert cues[0] == parse_cues(CUES)


def test_next_and_previous_clip_jump_between_cues_and_resend_color():
    player, backend, notifier = make()
    player.next_clip()
    assert backend.seeks == [10000]
    player.tick()
    assert notifier.sent[-1] == (0, 255, 0)
    player.next_clip()
    assert backend.seeks[-1] == 20500
    backend.time = 20600  # just entered the last clip: previous goes to the one before it
    player.previous_clip()
    assert backend.seeks[-1] == 10000
    backend.time = 15000  # well into the clip: previous restarts it
    player.previous_clip()
    assert backend.seeks[-1] == 10000


def test_next_clip_after_the_last_cue_goes_to_the_next_video_and_previous_before_first_goes_back():
    backend, notifier = Backend(), Notifier()
    player = PlaylistPlayer([Path("a.mp4"), Path("b.mp4")], backend, notifier, [(1, 1, 1)] * 2,
                            video_cues=[parse_cues(CUES), []])
    player.start()
    backend.time = 25000
    player.next_clip()
    assert player.index == 1  # no cue ahead
    player.next_clip()  # b has no cues: next video (wraps to a)
    assert player.index == 0
    backend.time = 500  # inside the first clip, barely started
    player.previous_clip()
    assert player.index == 1
