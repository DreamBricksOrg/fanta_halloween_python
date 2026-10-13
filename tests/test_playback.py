from pathlib import Path

from portrait_player.playback import PlaylistPlayer


class FakeBackend:
    def __init__(self):
        self.loaded = []
        self.paused = False

    def play(self, path, on_started):
        self.loaded.append(path)
        on_started()

    def pause(self):
        self.paused = not self.paused

    def stop(self):
        pass


class FakeNotifier:
    def __init__(self):
        self.events = []

    def playback_started(self, index, rgb):
        self.events.append((index, rgb))

    def close(self):
        pass


def test_each_actual_playback_start_notifies_once_and_controls_wrap_playlist():
    videos = (Path("a.mp4"), Path("b.mp4"), Path("c.mp4"))
    backend, notifier = FakeBackend(), FakeNotifier()
    player = PlaylistPlayer(videos, backend, notifier)

    player.start()
    assert notifier.events == [(0, (255, 96, 0))]
    player.next()
    assert notifier.events == [(0, (255, 96, 0)), (1, (190, 0, 120))]
    player.previous()
    assert notifier.events == [(0, (255, 96, 0)), (1, (190, 0, 120)), (0, (255, 96, 0))]
    player.pause_resume()
    assert backend.paused


def test_duplicate_start_event_for_same_playback_does_not_notify_twice():
    callbacks = []

    class DelayedBackend(FakeBackend):
        def play(self, path, on_started):
            callbacks.append(on_started)

    notifier = FakeNotifier()
    player = PlaylistPlayer((Path("a.mp4"),), DelayedBackend(), notifier)
    player.start()
    callbacks[0]()
    callbacks[0]()

    assert notifier.events == [(0, (255, 96, 0))]


def test_late_start_event_from_replaced_video_is_ignored():
    callbacks = []

    class DelayedBackend(FakeBackend):
        def play(self, path, on_started):
            callbacks.append(on_started)

    notifier = FakeNotifier()
    player = PlaylistPlayer((Path("a.mp4"), Path("b.mp4")), DelayedBackend(), notifier)
    player.start()
    player.next()
    callbacks[0]()
    callbacks[1]()

    assert notifier.events == [(1, (190, 0, 120))]


def test_single_video_restarts_when_end_event_arrives():
    video = Path("only.mp4")
    backend, notifier = FakeBackend(), FakeNotifier()
    player = PlaylistPlayer((video,), backend, notifier)

    player.start()
    backend.on_end()

    assert backend.loaded == [video, video]
    assert notifier.events == [(0, (255, 96, 0)), (0, (255, 96, 0))]


def test_end_events_advance_in_playlist_order_and_wrap_with_start_notifications():
    videos = tuple(Path(f"{name}.mp4") for name in "abc")
    backend, notifier = FakeBackend(), FakeNotifier()
    player = PlaylistPlayer(videos, backend, notifier)

    player.start()
    backend.on_end()
    backend.on_end()
    backend.on_end()

    assert backend.loaded == [videos[0], videos[1], videos[2], videos[0]]
    assert notifier.events == [(0, (255, 96, 0)), (1, (190, 0, 120)), (2, (72, 0, 255)), (0, (255, 96, 0))]
