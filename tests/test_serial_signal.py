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

    notifier.send_rgb((255, 96, 0))
    notifier.send_rgb((190, 0, 120))

    assert serial.writes == [b"RGB(255,96,0)\n", b"RGB(190,0,120)\n"]


def test_each_playback_start_sends_restart_1_then_the_color():
    serial = FakeSerial()
    notifier = SerialNotifier(serial)

    notifier.playback_started(0, (255, 96, 0))
    notifier.playback_started(0, (255, 96, 0))  # the video looped

    assert serial.writes == [b"1\n", b"RGB(255,96,0)\n"] * 2


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
    assert serial.writes == [b"1\n", b"RGB(255,96,0)\n", b"1\n", b"RGB(190,0,120)\n"]


def test_disabled_notifier_does_not_require_hardware():
    notifier = SerialNotifier.disabled()

    notifier.playback_started(3, (1, 2, 3))
    notifier.close()


def test_poll_records_arduino_acks_and_write_failure_marks_port_disconnected():
    from portrait_player.telemetry import Telemetry

    class Port(FakeSerial):
        in_waiting = 0
        is_open = True
        fail = False

        def write(self, payload):
            if self.fail:
                raise OSError("unplugged")
            super().write(payload)

        def read(self, n):
            return b"OK RGB(1,2,3)\r\n"

    telemetry = Telemetry()
    port = Port()
    notifier = SerialNotifier(port, telemetry, port="COM9")
    assert notifier.send_rgb((1, 2, 3))
    port.in_waiting = 15
    notifier.poll()
    assert notifier.last_ack == "OK RGB(1,2,3)"
    port.fail = True
    assert not notifier.send_rgb((4, 5, 6))
    assert not notifier.status()["connected"] and "unplugged" in notifier.status()["last_error"]
