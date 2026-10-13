"""Playlist state and controls, independent of the VLC runtime."""


class PlaylistPlayer:
    def __init__(self, videos, backend, notifier, video_rgbs=None):
        if not videos:
            raise ValueError("playlist must contain at least one video")
        self.videos = tuple(videos)
        self.backend = backend
        self.notifier = notifier
        self.video_rgbs = tuple(video_rgbs or ((255, 96, 0), (190, 0, 120), (72, 0, 255)))
        self.index = 0
        self._generation = 0
        self._started_generation = None
        self.backend.on_end = self.next

    def _play_current(self):
        self._generation += 1
        generation = self._generation
        index = self.index

        def started():
            # A queued event from a replaced media item must not signal its index.
            if generation != self._generation:
                return
            if self._started_generation != generation:
                self._started_generation = generation
                self.notifier.playback_started(index, self.video_rgbs[index % len(self.video_rgbs)])

        self.backend.play(self.videos[self.index], started)

    def start(self):
        self._play_current()

    def next(self):
        self.index = (self.index + 1) % len(self.videos)
        self._play_current()

    def previous(self):
        self.index = (self.index - 1) % len(self.videos)
        self._play_current()

    def pause_resume(self):
        self.backend.pause()

    def close(self):
        self.backend.stop()
        self.notifier.close()
