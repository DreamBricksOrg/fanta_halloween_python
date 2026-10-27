"""VLC adapter. python-vlc is imported only when a real player is created."""

from queue import Empty, SimpleQueue


class VLCBackend:
    def __init__(self, video_widget):
        try:
            import vlc
        except ImportError as exc:
            raise RuntimeError("python-vlc is required; install requirements.txt") from exc
        self._vlc = vlc
        self._instance = vlc.Instance()
        self._player = self._instance.media_player_new()
        self._widget = video_widget
        self.on_end = lambda: None
        self._pending_events = SimpleQueue()
        if hasattr(video_widget, "winfo_id"):
            handle = video_widget.winfo_id()
            if hasattr(self._player, "set_hwnd"):
                self._player.set_hwnd(handle)
            elif hasattr(self._player, "set_xwindow"):
                self._player.set_xwindow(handle)
            else:
                self._player.set_nsobject(handle)
        self._player.event_manager().event_attach(
            vlc.EventType.MediaPlayerEndReached,
            lambda event: self._pending_events.put(None),
        )
        if hasattr(self._player, "video_set_key_input"):
            self._player.video_set_key_input(False)

    def play(self, path, on_started):
        media = self._instance.media_new(str(path))
        self._player.set_media(media)
        manager = self._player.event_manager()
        manager.event_attach(self._vlc.EventType.MediaPlayerPlaying, lambda event: on_started())
        self._player.play()

    def pause(self):
        self._player.pause()

    def get_time(self):
        return self._player.get_time()

    def get_length(self):
        return self._player.get_length()

    def set_time(self, ms):
        self._player.set_time(ms)

    def set_pause(self, paused):
        self._player.set_pause(1 if paused else 0)

    def stop(self):
        self._player.stop()

    def process_events(self):
        """Deliver VLC worker-thread events from the caller's (Tk) thread."""
        while True:
            try:
                self._pending_events.get_nowait()
            except Empty:
                break
            self.on_end()
