"""Playlist state and controls, independent of the VLC runtime."""

from bisect import bisect_right
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


def parse_cues(cues):
    """Validate [{"t": seconds, "rgb": [r, g, b]}] into a time-sorted list of (ms, rgb)."""
    if not isinstance(cues, (list, tuple)):
        raise ValueError("cues deve ser uma lista")
    parsed = []
    for cue in cues:
        try:
            t, rgb = cue["t"], cue["rgb"]
        except (TypeError, KeyError):
            raise ValueError("cada cue precisa de t (segundos) e rgb")
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not 0 <= t <= 86400:
            raise ValueError("tempo do cue inválido")
        parsed.append((int(round(t * 1000)), check_rgb(rgb)))
    parsed.sort(key=lambda cue: cue[0])
    if any(a[0] == b[0] for a, b in zip(parsed, parsed[1:])):
        raise ValueError("dois cues no mesmo instante")
    return parsed


class PlaylistPlayer:
    def __init__(self, videos, backend, notifier, video_rgbs=None, on_event=_noop, on_change=_noop,
                 video_cues=None, cue_lead_ms=0):
        if not videos:
            raise ValueError("playlist must contain at least one video")
        self.videos = list(videos)
        rgbs = tuple(video_rgbs or DEFAULT_RGBS)
        self.video_rgbs = [tuple(rgbs[i % len(rgbs)]) for i in range(len(self.videos))]
        cues = list(video_cues or [])
        self.video_cues = [list(cues[i]) if i < len(cues) else [] for i in range(len(self.videos))]
        self.cue_lead_ms = cue_lead_ms  # fire cues early to absorb latency / the Arduino fade
        self._active_cue = None  # index of the cue whose color is on the LEDs; None = unknown
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
        self._active_cue = None

        def started():
            # A queued event from a replaced media item must not signal its index.
            if generation != self._generation:
                return
            if self._started_generation != generation:
                self._started_generation = generation
                rgb = self._color_at(index, 0)
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

    # --- timeline cues ----------------------------------------------------

    def _position_ms(self):
        get_time = getattr(self.backend, "get_time", None)
        return max(0, get_time()) if get_time else 0

    def _cue_slot(self, index, pos_ms):
        """Index of the cue active at pos_ms (-1 before the first cue)."""
        cues = self.video_cues[index]
        return bisect_right([t for t, _ in cues], pos_ms) - 1

    def _color_at(self, index, pos_ms):
        slot = self._cue_slot(index, pos_ms)
        if index == self.index:
            self._active_cue = slot
        return self.video_cues[index][slot][1] if slot >= 0 else self.video_rgbs[index]

    def tick(self):
        """Called often from the Tk loop: fire the cue whose time was just reached."""
        if self.led_mode or self._stale_media or self._started_generation != self._generation:
            return
        pos = self._position_ms() + self.cue_lead_ms
        slot = self._cue_slot(self.index, pos)
        if slot == self._active_cue:
            return
        previous, self._active_cue = self._active_cue, slot
        if slot >= 0:
            t, rgb = self.video_cues[self.index][slot]
            self.on_event("cue", f"{t / 1000:.2f}s → RGB{rgb}")
            self.notifier.send_rgb(rgb, f"cue {t / 1000:.2f}s")
        elif previous is not None:  # sought back before the first cue
            self.notifier.send_rgb(self.video_rgbs[self.index], "início do vídeo")

    def seek(self, seconds):
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds < 0:
            raise ValueError("tempo inválido")
        self.backend.set_time(int(seconds * 1000))
        self._active_cue = None  # the next tick re-sends the color for the new position

    def set_cues(self, index, cues):
        self._check_index(index)
        self.video_cues[index] = parse_cues(cues)
        self.on_event("playlist", f"{len(self.video_cues[index])} cues no vídeo #{index}")
        self.on_change()
        if index == self.index:
            self._active_cue = None

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
        self.video_cues.append([])
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
        del self.video_cues[index]
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
        self.video_cues.insert(dst, self.video_cues.pop(src))
        self.index = cur
        self.on_event("playlist", f"movido #{src} → #{dst}")
        self.on_change()

    def set_rgb(self, index, rgb):
        self._check_index(index)
        self.video_rgbs[index] = check_rgb(rgb)
        self.on_event("playlist", f"cor do vídeo #{index} = RGB{self.video_rgbs[index]}")
        self.on_change()
        if index == self.index and not self.led_mode:
            self._active_cue = None
            if self._cue_slot(index, self._position_ms()) < 0:  # a cue's color wins over the base color
                self.notifier.send_rgb(self.video_rgbs[index], "cor editada")

    # --- LED test mode ----------------------------------------------------

    def set_led_mode(self, enabled):
        enabled = bool(enabled)
        if enabled == self.led_mode:
            return
        self.led_mode = enabled
        if enabled:
            self.backend.set_pause(True)
            self.led_rgb = self._color_at(self.index, self._position_ms())
            self.on_event("led", "modo LED ligado (vídeo pausado)")
            self.notifier.send_rgb(self.led_rgb, "modo LED")
        else:
            self.on_event("led", "modo LED desligado")
            if self._stale_media:
                self._play_current()
            else:
                if not self.paused:
                    self.backend.set_pause(False)
                self.notifier.send_rgb(self._color_at(self.index, self._position_ms()), "fim do modo LED")

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
                    "cues": [{"t": t / 1000, "rgb": list(rgb)} for t, rgb in self.video_cues[i]],
                    "exists": Path(str(v)).exists(),
                }
                for i, v in enumerate(self.videos)
            ],
            "current": self.index,
            "paused": self.paused,
            "led_mode": self.led_mode,
            "led_rgb": list(self.led_rgb),
            "position_ms": self._position_ms(),
            "length_ms": max(0, getattr(self.backend, "get_length", lambda: 0)()),
        }

    def close(self):
        self.backend.stop()
        self.notifier.close()
