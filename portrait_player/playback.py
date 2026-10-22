"""Playlist state and controls, independent of the VLC runtime."""

from pathlib import Path

DEFAULT_RGBS = ((255, 96, 0), (190, 0, 120), (72, 0, 255))


def _noop(*args, **kwargs):
    pass


def check_rgb(rgb):
    try:
        channels = tuple(rgb)
    except TypeError:
        raise ValueError("RGB must contain three channels from 0 to 255")
    if len(channels) != 3 or any(not isinstance(c, int) or isinstance(c, bool) or not 0 <= c <= 255 for c in channels):
        raise ValueError("RGB must contain three channels from 0 to 255")
    return channels


class PlaylistPlayer:
    def __init__(self, videos, backend, notifier, video_rgbs=None, on_event=_noop, on_change=_noop):
        if not videos:
            raise ValueError("playlist must contain at least one video")
        self.videos = list(videos)
        rgbs = tuple(video_rgbs or DEFAULT_RGBS)
        self.video_rgbs = [tuple(rgbs[i % len(rgbs)]) for i in range(len(self.videos))]
        self.backend = backend
        self.notifier = notifier
        self.on_event = on_event
        self.on_change = on_change
        self.index = 0
        self.paused = False
        self.led_mode = False
        self.led_rgb = (0, 0, 0)
        self._stale_media = False
        self._generation = 0
        self._started_generation = None
        self.backend.on_end = self.next

    def _play_current(self):
        self._generation += 1
        generation = self._generation
        index = self.index
        self.led_mode = False
        self.paused = False
        self._stale_media = False

        def started():
            # A queued event from a replaced media item must not signal its index.
            if generation != self._generation:
                return
            if self._started_generation != generation:
                self._started_generation = generation
                rgb = self.video_rgbs[index]
                self.on_event("video", f"#{index} {Path(str(self.videos[index])).name} iniciou")
                self.notifier.playback_started(index, rgb)

        self.backend.play(self.videos[self.index], started)

    def start(self):
        self._play_current()

    def next(self):
        self.index = (self.index + 1) % len(self.videos)
        self._play_current()

    def previous(self):
        self.index = (self.index - 1) % len(self.videos)
        self._play_current()

    def play_index(self, index):
        self._check_index(index)
        self.index = index
        self._play_current()

    def pause_resume(self):
        self.paused = not self.paused
        self.backend.pause()

    def _check_index(self, index):
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(self.videos):
            raise ValueError("video index out of range")

    def _default_rgb(self, index):
        return DEFAULT_RGBS[index % len(DEFAULT_RGBS)]

    # --- playlist editing -------------------------------------------------

    def add(self, path, rgb=None):
        rgb = check_rgb(rgb) if rgb is not None else self._default_rgb(len(self.videos))
        self.videos.append(Path(path))
        self.video_rgbs.append(rgb)
        self.on_event("playlist", f"adicionado {Path(path).name}")
        self.on_change()
        return len(self.videos) - 1

    def remove(self, index):
        self._check_index(index)
        if len(self.videos) == 1:
            raise ValueError("a playlist precisa de pelo menos um vídeo")
        name = Path(str(self.videos[index])).name
        del self.videos[index]
        del self.video_rgbs[index]
        replaced = False
        if index < self.index:
            self.index -= 1
        elif index == self.index:
            self.index %= len(self.videos)  # the next video slides into this slot
            replaced = True
        self.on_event("playlist", f"removido {name}")
        self.on_change()
        if replaced:
            if self.led_mode:
                self._stale_media = True
            else:
                self._play_current()

    def move(self, src, dst):
        self._check_index(src)
        self._check_index(dst)
        if src == dst:
            return
        cur = self.index
        if src == cur:
            cur = dst
        elif src < cur <= dst:
            cur -= 1
        elif dst <= cur < src:
            cur += 1
        self.videos.insert(dst, self.videos.pop(src))
        self.video_rgbs.insert(dst, self.video_rgbs.pop(src))
        self.index = cur
        self.on_event("playlist", f"movido #{src} → #{dst}")
        self.on_change()

    def set_rgb(self, index, rgb):
        self._check_index(index)
        self.video_rgbs[index] = check_rgb(rgb)
        self.on_event("playlist", f"cor do vídeo #{index} = RGB{self.video_rgbs[index]}")
        self.on_change()
        if index == self.index and not self.led_mode:
            self.notifier.send_rgb(self.video_rgbs[index], "cor editada")

    # --- LED test mode ----------------------------------------------------

    def set_led_mode(self, enabled):
        enabled = bool(enabled)
        if enabled == self.led_mode:
            return
        self.led_mode = enabled
        if enabled:
            self.backend.set_pause(True)
            self.led_rgb = self.video_rgbs[self.index]
            self.on_event("led", "modo LED ligado (vídeo pausado)")
            self.notifier.send_rgb(self.led_rgb, "modo LED")
        else:
            self.on_event("led", "modo LED desligado")
            if self._stale_media:
                self._play_current()
            else:
                if not self.paused:
                    self.backend.set_pause(False)
                self.notifier.send_rgb(self.video_rgbs[self.index], "fim do modo LED")

    def send_led(self, rgb):
        rgb = check_rgb(rgb)
        self.set_led_mode(True)
        self.led_rgb = rgb
        self.notifier.send_rgb(rgb, "modo LED")

    def state(self):
        return {
            "playlist": [
                {
                    "index": i,
                    "name": Path(str(v)).name,
                    "path": str(v),
                    "rgb": list(self.video_rgbs[i]),
                    "exists": Path(str(v)).exists(),
                }
                for i, v in enumerate(self.videos)
            ],
            "current": self.index,
            "paused": self.paused,
            "led_mode": self.led_mode,
            "led_rgb": list(self.led_rgb),
        }

    def close(self):
        self.backend.stop()
        self.notifier.close()
