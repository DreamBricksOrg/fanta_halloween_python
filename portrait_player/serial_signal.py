"""Optional Arduino serial playback notifications."""

from __future__ import annotations

import time

RECONNECT_INTERVAL_S = 3.0
RESTART_MESSAGE = "1"


def _check_rgb(rgb) -> None:
    if len(rgb) != 3 or any(not isinstance(channel, int) or not 0 <= channel <= 255 for channel in rgb):
        raise ValueError("RGB must contain three channels from 0 to 255")


class SerialNotifier:
    def __init__(self, connection=None, telemetry=None, port=None, baud=115200):
        self._connection = connection
        self._telemetry = telemetry
        self._port = port
        self._baud = baud
        self._rx = b""
        self._last_attempt = 0.0
        self.last_write_at = None
        self.last_message = None
        self.last_ack_at = None
        self.last_ack = None
        self.last_error = None
        self.last_rgb = None

    @classmethod
    def disabled(cls, telemetry=None):
        return cls(telemetry=telemetry)

    @classmethod
    def open(cls, port: str | None, baud: int = 115200, telemetry=None):
        if not port:
            return cls.disabled(telemetry)
        try:
            import serial  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("Serial output requires pyserial; install requirements.txt") from exc
        notifier = cls(telemetry=telemetry, port=port, baud=baud)
        # A missing device at startup is not fatal: the control panel shows it and we keep retrying.
        notifier._connect()
        return notifier

    def _log(self, kind: str, text: str, ok: bool = True) -> None:
        if self._telemetry is not None:
            self._telemetry.event(kind, text, ok)

    def _connect(self) -> bool:
        import serial

        self._last_attempt = time.monotonic()
        try:
            self._connection = serial.Serial(self._port, self._baud, timeout=0)
        except (serial.SerialException, OSError) as exc:
            self._connection = None
            self.last_error = str(exc)
            return False
        self.last_error = None
        self._log("serial", f"porta {self._port} aberta")
        return True

    def _drop(self, exc: Exception) -> None:
        self.last_error = str(exc)
        self._log("serial", f"falha na porta serial: {exc}", ok=False)
        try:
            self._connection.close()
        except Exception:
            pass
        self._connection = None

    @property
    def connected(self) -> bool:
        return self._connection is not None and getattr(self._connection, "is_open", True)

    def send_rgb(self, rgb, source: str = "") -> bool:
        """Write one RGB command; returns whether it reached the serial port."""
        _check_rgb(rgb)
        self.last_rgb = tuple(rgb)
        return self._send(f"RGB({rgb[0]},{rgb[1]},{rgb[2]})", source)

    def _send(self, message: str, source: str = "") -> bool:
        if not self.connected:
            if self._port:
                self._log("serial_tx", f"{message} não enviado (porta desconectada)", ok=False)
            return False
        try:
            self._connection.write(f"{message}\n".encode("ascii"))
        except Exception as exc:
            self._drop(exc)
            self._log("serial_tx", f"{message} falhou", ok=False)
            return False
        self.last_write_at = time.time()
        self.last_message = message
        self._log("serial_tx", f"{message}" + (f" ({source})" if source else ""))
        return True

    def playback_started(self, index: int, rgb: tuple[int, int, int]) -> None:
        if index < 0:
            raise ValueError("playlist index cannot be negative")
        _check_rgb(rgb)
        # "1" tells the Arduino the video (re)started; the color follows right after.
        self._send(RESTART_MESSAGE, f"vídeo {index} reiniciou")
        self.send_rgb(rgb, f"vídeo {index}")

    def poll(self) -> bool:
        """Read Arduino replies and retry a lost port. Returns True when (re)connected just now."""
        if not self._port:
            return False
        if not self.connected:
            if time.monotonic() - self._last_attempt >= RECONNECT_INTERVAL_S:
                return self._connect()
            return False
        try:
            waiting = self._connection.in_waiting
            data = self._connection.read(waiting) if waiting else b""
        except Exception as exc:
            self._drop(exc)
            return False
        self._rx = (self._rx + data)[-256:]
        while b"\n" in self._rx:
            line, self._rx = self._rx.split(b"\n", 1)
            text = line.decode("ascii", "replace").strip()
            if text:
                self.last_ack_at = time.time()
                self.last_ack = text
                self._log("arduino_rx", text, ok=not text.startswith("ERR"))
        return False

    def status(self) -> dict:
        return {
            "configured": bool(self._port),
            "port": self._port,
            "baud": self._baud,
            "connected": bool(self.connected),
            "last_write_at": self.last_write_at,
            "last_message": self.last_message,
            "last_ack_at": self.last_ack_at,
            "last_ack": self.last_ack,
            "last_error": self.last_error,
        }

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
