from portrait_player.serial_signal import SerialNotifier


class FakeSerial:
    def __init__(self):
        self.writes = []
        self.closed = False

    def write(self, payload):
        self.writes.append(payload)

    def close(self):
        self.closed = True


def test_notifies_arduino_with_only_ascii_index_and_newline():
    serial = FakeSerial()
    notifier = SerialNotifier(serial)

    notifier.playback_started(0)
    notifier.playback_started(12)

    assert serial.writes == [b"0\n", b"12\n"]


def test_disabled_notifier_does_not_require_hardware():
    notifier = SerialNotifier.disabled()

    notifier.playback_started(3)
    notifier.close()
