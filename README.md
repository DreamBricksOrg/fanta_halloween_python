# Portrait Playlist Player

A small Python desktop player that displays a VLC playlist in a 9:16 portrait window. It can optionally send each playing video's configured RGB color to an Arduino over serial.

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
| `VIDEO_0_RGB` | RGB channels for the first video, comma-separated | `255,96,0` |
| `VIDEO_1_RGB` | RGB channels for the second video, comma-separated | `190,0,120` |
| `VIDEO_2_RGB` | RGB channels for the third video, comma-separated | `72,0,255` |
| `SERIAL_PORT` | Serial port name, such as `COM4` or `/dev/ttyACM0` | Blank (disabled) |
| `SERIAL_BAUD` | Serial baud rate | `115200` |

When a video begins playback, the player sends its actual RGB values as ASCII `RGB(r,g,b)` followed by newline. For the first video's default color this is `b"RGB(255,96,0)\\n"`. Each channel must be an integer from 0 to 255. Missing color keys use the defaults above; change these keys in `.env` without recompiling firmware. A port is never assumed; configure one only when serial output is wanted.

### DMX lighting sketch

The `arduino/fanta_halloween_dmx/fanta_halloween_dmx.ino` sketch uses the DmxSimple library, DMX output on pin 13, and DMX start channel 1. It drives ten RGB groups (30 consecutive channels) and accepts only strict newline-terminated `RGB(r,g,b)` commands at 115200 baud, with each channel from 0 to 255 (for example, `RGB(255,96,0)\\n`). LF and CRLF line endings are accepted. Color changes fade over 500 ms. The last selected color remains active (no input timeout). The sketch replies `READY` on boot, `OK RGB(r,g,b)` for each accepted command and `ERR` for a rejected line; the control panel uses these replies to confirm delivery (re-flash the sketch to get them; older firmware still works, just without confirmation).

Set `SERIAL_PORT` to the Arduino's port in `.env` to enable serial output. The baud rate must match the sketch (`SERIAL_BAUD=115200`).

## Run and controls

```sh
python -m portrait_player
```

The app launches fullscreen. Video is displayed in a centered 9:16 portrait viewport, with black bars on landscape screens to preserve the image's aspect ratio. The playlist advances automatically and loops continuously, including when it contains only one video. No controls or command hints are shown by default. Press **D** to show or hide the debug footer and its Previous, Pause / Resume, and Next buttons. Keyboard shortcuts remain available: **D** = toggle debug footer, **Left** = previous, **Right** = next, **Space** = pause/resume, and **Escape** = quit.

## Control panel

Starting the app also starts a web panel at <http://127.0.0.1:8080> (`CONTROL_HOST` / `CONTROL_PORT` in `.env`; `CONTROL_PORT=0` disables it; use `CONTROL_HOST=0.0.0.0` to reach it from a phone on the same network — there is no login, so only do this on a trusted network).

- **Playlist**: add videos (upload from the browser into `videos/`, or a path already on the PC), remove them (the file is not deleted), reorder by dragging or with the arrows, play any video now, and set each video's LED color. Changes apply immediately and are saved to `playlist_state.json`, which takes precedence over `VIDEO_N` in `.env` once it exists (delete it to go back to `.env`). Reordering never restarts the playing video; removing the playing one starts the next.
- **LED mode**: pauses the video and sends the RGB you pick (sliders, picker, presets) straight to the LEDs. Leaving it resumes the video and restores its color.
- **Telemetry**: app uptime, serial port state (reconnects automatically if unplugged), the last message sent, whether the Arduino confirmed it, what is playing, counters and an event log (video started → `RGB(...)` sent → Arduino `OK`).

## Tests and optional hardware smoke test

Automated tests use fakes and do not require VLC or an Arduino:

```sh
python -m pytest -q
```

For an optional playback smoke test, install VLC's runtime, put a short portrait clip at a configured path, leave `SERIAL_PORT` blank, and run the command above. To check the Arduino signal, set `SERIAL_PORT` to the correct device and baud; observe one newline-terminated `RGB(r,g,b)` command per playback start.
