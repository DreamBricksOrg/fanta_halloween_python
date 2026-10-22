from pathlib import Path

import pytest

from portrait_player.playback import PlaylistPlayer


class Backend:
    def __init__(self):
        self.loaded = []
        self.pauses = []

    def play(self, path, on_started):
        self.loaded.append(path)
        on_started()

    def pause(self):
        pass

    def set_pause(self, paused):
        self.pauses.append(paused)

    def stop(self):
        pass


class Notifier:
    def __init__(self):
        self.sent = []

    def playback_started(self, index, rgb):
        self.sent.append(("start", index, rgb))

    def send_rgb(self, rgb, source=""):
        self.sent.append(("rgb", tuple(rgb)))

    def close(self):
        pass


def make(n=3):
    videos = [Path(f"{c}.mp4") for c in "abcdef"[:n]]
    backend, notifier = Backend(), Notifier()
    changes = []
    player = PlaylistPlayer(videos, backend, notifier, on_change=lambda: changes.append(1))
    player.start()
    return player, backend, notifier, changes


def names(player):
    return [v.stem for v in player.videos]


def test_move_keeps_current_video_playing_and_carries_colors():
    player, backend, _, changes = make()
    player.next()  # b is current
    loaded = len(backend.loaded)
    player.move(0, 2)  # a to the end -> b c a
    assert names(player) == ["b", "c", "a"]
    assert player.index == 0
    assert player.video_rgbs[2] == (255, 96, 0)
    player.move(0, 1)  # current b moves with it
    assert names(player) == ["c", "b", "a"] and player.index == 1
    assert len(backend.loaded) == loaded  # reordering never restarts playback
    assert len(changes) == 2


def test_remove_current_plays_the_video_that_slides_into_its_slot():
    player, backend, _, _ = make()
    player.next()
    player.remove(1)
    assert names(player) == ["a", "c"] and player.index == 1
    assert backend.loaded[-1] == Path("c.mp4")


def test_remove_before_current_shifts_index_without_restart():
    player, backend, _, _ = make()
    player.next()
    player.next()
    loaded = len(backend.loaded)
    player.remove(0)
    assert player.index == 1 and names(player) == ["b", "c"]
    assert len(backend.loaded) == loaded


def test_cannot_remove_last_video_or_bad_index():
    player, _, _, _ = make(1)
    with pytest.raises(ValueError):
        player.remove(0)
    with pytest.raises(ValueError):
        player.play_index(5)


def test_add_and_set_rgb_live_updates_current_color():
    player, _, notifier, _ = make(1)
    assert player.add("new.mp4") == 1
    player.set_rgb(0, (1, 2, 3))
    assert notifier.sent[-1] == ("rgb", (1, 2, 3))
    player.set_rgb(1, (9, 9, 9))
    assert notifier.sent[-1] == ("rgb", (1, 2, 3))  # not the playing video
    with pytest.raises(ValueError):
        player.set_rgb(0, (1, 2, 256))


def test_led_mode_pauses_sends_color_and_restores_video_color():
    player, backend, notifier, _ = make()
    player.send_led((10, 20, 30))
    assert player.led_mode and backend.pauses == [True]
    assert notifier.sent[-1] == ("rgb", (10, 20, 30))
    player.set_led_mode(False)
    assert backend.pauses == [True, False]
    assert notifier.sent[-1] == ("rgb", (255, 96, 0))


def test_led_mode_does_not_resume_video_the_user_paused():
    player, backend, _, _ = make()
    player.pause_resume()
    player.send_led((1, 1, 1))
    player.set_led_mode(False)
    assert backend.pauses == [True]


def test_removing_current_video_during_led_mode_replays_on_exit():
    player, backend, _, _ = make()
    player.send_led((1, 1, 1))
    loaded = len(backend.loaded)
    player.remove(0)
    assert len(backend.loaded) == loaded
    player.set_led_mode(False)
    assert backend.loaded[-1] == Path("b.mp4")
