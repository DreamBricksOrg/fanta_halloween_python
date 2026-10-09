"""Optional Arduino serial playback notifications."""


class SerialNotifier:
    def __init__(self, connection=None):
        self._connection = connection

    @classmethod
    def disabled(cls):
        return cls()

    @classmethod
    def open(cls, port: str | None, baud: int = 9600):
        if not port:
            return cls.disabled()
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("Serial output requires pyserial; install requirements.txt") from exc
        return cls(serial.Serial(port, baud, timeout=1))

    def playback_started(self, index: int) -> None:
        if index < 0:
            raise ValueError("playlist index cannot be negative")
        if self._connection is not None:
            self._connection.write(f"{index}\n".encode("ascii"))

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
