# Portrait Playlist Player

A small Python desktop player that displays a VLC playlist in a 9:16 portrait window. It can optionally send each playing video's zero-based playlist index to an Arduino over serial.

## Prerequisites

- Python 3.10 or newer.
- The VLC desktop/runtime installation for your operating system. `python-vlc` is only a Python binding; it does **not** include VLC's native runtime. Install VLC and make sure its shared libraries are discoverable (`libvlc.dll` on Windows).
- Optional: an Arduino or other serial device for playback-start signals.

## Setup

From the project root:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and edit the video paths. Put videos wherever you prefer; video files are excluded from Git.

## Configuration

Playlist entries use `VIDEO_N` keys, ordered numerically (not by textual sorting). `VIDEO_0` is required; add `VIDEO_3`, `VIDEO_4`, and so on for longer playlists. Relative paths resolve from the project root, regardless of the current working directory.

| Variable | Meaning | Default |
| --- | --- | --- |
| `VIDEO_0`, `VIDEO_1`, … | Video paths in playlist order | Required |
| `SERIAL_PORT` | Serial port name, such as `COM4` or `/dev/ttyACM0` | Blank (disabled) |
| `SERIAL_BAUD` | Serial baud rate | `115200` |

When a video begins playback, the player sends only its playlist index as ASCII digits followed by a newline. For the first video that is `b"0\\n"`, equivalent to Arduino `Serial.println("0");`. A port is never assumed; configure one only when serial output is wanted.

### DMX lighting sketch

The `arduino/fanta_halloween_dmx/fanta_halloween_dmx.ino` sketch uses the DmxSimple library, DMX output on pin 13, and DMX start channel 1. It drives ten RGB groups (30 consecutive channels) and listens for newline-delimited color IDs at 115200 baud: `0` = orange (RGB 255, 96, 0), `1` = reddish purple (RGB 190, 0, 120), and `2` = blue purple (RGB 72, 0, 255). Color changes fade over 500 ms. The sketch sends no serial output and has no input timeout, so the last selected color remains active.

Before using the sketch, manually set `SERIAL_BAUD=115200` in your ignored local `.env`; `.env.example` documents the value but does not change the local file. Set `SERIAL_PORT` to the Arduino's port as well.

## Run and controls

```sh
python -m portrait_player
```

The app launches fullscreen. Video is displayed in a centered 9:16 portrait viewport, with black bars on landscape screens to preserve the image's aspect ratio. The playlist advances automatically and loops continuously, including when it contains only one video. No controls or command hints are shown by default. Press **D** to show or hide the debug footer and its Previous, Pause / Resume, and Next buttons. Keyboard shortcuts remain available: **D** = toggle debug footer, **Left** = previous, **Right** = next, **Space** = pause/resume, and **Escape** = quit.

## Tests and optional hardware smoke test

Automated tests use fakes and do not require VLC or an Arduino:

```sh
python -m pytest -q
```

For an optional playback smoke test, install VLC's runtime, put a short portrait clip at a configured path, leave `SERIAL_PORT` blank, and run the command above. To check the Arduino signal, set `SERIAL_PORT` to the correct device and baud; use a serial monitor that expects one newline-terminated numeric index per playback start.
