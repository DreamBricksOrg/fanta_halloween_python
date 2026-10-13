from portrait_player.serial_signal import SerialNotifier


class FakeSerial:
    def __init__(self):
        self.writes = []
        self.closed = False

    def write(self, payload):
        self.writes.append(payload)

    def close(self):
        self.closed = True


def test_notifies_arduino_with_exact_rgb_ascii_and_newline():
    serial = FakeSerial()
    notifier = SerialNotifier(serial)

    notifier.playback_started(0, (255, 96, 0))
    notifier.playback_started(1, (190, 0, 120))

    assert serial.writes == [b"RGB(255,96,0)\n", b"RGB(190,0,120)\n"]


def test_playback_event_sends_rgb_once_for_each_start():
    from portrait_player.playback import PlaylistPlayer

    class Backend:
        def play(self, video, on_started):
            on_started()
            on_started()

        def pause(self):
            pass

        def stop(self):
            pass

    serial = FakeSerial()
    player = PlaylistPlayer(("one", "two"), Backend(), SerialNotifier(serial))
    player.start()
    player.next()
    assert serial.writes == [b"RGB(255,96,0)\n", b"RGB(190,0,120)\n"]


def test_disabled_notifier_does_not_require_hardware():
    notifier = SerialNotifier.disabled()

    notifier.playback_started(3, (1, 2, 3))
    notifier.close()
