"""Optional Arduino serial playback notifications."""


class SerialNotifier:
    def __init__(self, connection=None):
        self._connection = connection

    @classmethod
    def disabled(cls):
        return cls()

    @classmethod
    def open(cls, port: str | None, baud: int = 115200):
        if not port:
            return cls.disabled()
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("Serial output requires pyserial; install requirements.txt") from exc
        return cls(serial.Serial(port, baud, timeout=1))

    def playback_started(self, index: int, rgb: tuple[int, int, int]) -> None:
        if index < 0:
            raise ValueError("playlist index cannot be negative")
        if len(rgb) != 3 or any(not isinstance(channel, int) or not 0 <= channel <= 255 for channel in rgb):
            raise ValueError("RGB must contain three channels from 0 to 255")
        if self._connection is not None:
            self._connection.write(f"RGB({rgb[0]},{rgb[1]},{rgb[2]})\n".encode("ascii"))

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
