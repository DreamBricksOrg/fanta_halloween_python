"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re

from .playback import parse_cues


class ConfigError(ValueError):
    """Raised when the player configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    videos: tuple[Path, ...]
    video_rgbs: tuple[tuple[int, int, int], ...]
    serial_port: str | None = None
    serial_baud: int = 115200
    control_host: str = "127.0.0.1"
    control_port: int = 8080
    cue_lead_ms: int = 0
    video_cues: tuple = ()


_VIDEO_KEY = re.compile(r"^VIDEO_(\d+)$")
_RGB_DEFAULTS = ((255, 96, 0), (190, 0, 120), (72, 0, 255))


def _parse_rgb(key: str, value: str) -> tuple[int, int, int]:
    try:
        channels = tuple(int(channel.strip()) for channel in value.split(","))
    except ValueError as exc:
        raise ConfigError(f"{key} must contain three integer channels from 0 to 255") from exc
    if len(channels) != 3 or any(channel < 0 or channel > 255 for channel in channels):
        raise ConfigError(f"{key} must contain three integer channels from 0 to 255")
    return channels


def _parse_cues(key: str, value: str):
    """VIDEO_N_CUES=0:255,96,0;60:190,0,120 -> time in seconds, then the RGB at that time."""
    cues = []
    for part in filter(None, (p.strip() for p in value.split(";"))):
        seconds, _, rgb = part.partition(":")
        try:
            cues.append({"t": float(seconds), "rgb": [int(c) for c in rgb.split(",")]})
        except ValueError as exc:
            raise ConfigError(f"{key} must look like 0:255,96,0;60:190,0,120 (seconds:r,g,b)") from exc
    try:
        return tuple(parse_cues(cues))
    except ValueError as exc:
        raise ConfigError(f"{key}: {exc}") from exc


def _parse_clips(key: str, value: str):
    """VIDEO_N_CLIPS=60:255,96,0;45:190,0,120 -> clip length in seconds, then its color.

    Cue times are the running total of the lengths, so changing one length shifts the later clips.
    """
    cues, start = [], 0.0
    for part in filter(None, (p.strip() for p in value.split(";"))):
        seconds, _, rgb = part.partition(":")
        try:
            length = float(seconds)
            cues.append({"t": start, "rgb": [int(c) for c in rgb.split(",")]})
        except ValueError as exc:
            raise ConfigError(f"{key} must look like 60:255,96,0;60:190,0,120 (seconds:r,g,b per clip)") from exc
        if length <= 0:
            raise ConfigError(f"{key}: clip lengths must be greater than 0")
        start += length
    try:
        return tuple(parse_cues(cues))
    except ValueError as exc:
        raise ConfigError(f"{key}: {exc}") from exc


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ConfigError(f"Cannot read configuration file {path}: {exc}") from exc
    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ConfigError(f"Invalid configuration at {path}:{line_number}")
        key, value = (part.strip() for part in line.split("=", 1))
        if not key:
            raise ConfigError(f"Invalid configuration at {path}:{line_number}")
        value = value.split(" #", 1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load_config(env_file: str | Path = ".env", project_root: str | Path | None = None) -> Config:
    """Read playlist values from a dotenv-style file and resolve videos from root."""
    env_path = Path(env_file)
    root = Path(project_root) if project_root is not None else Path.cwd()
    root = root.resolve()
    values = _read_env(env_path)
    # Process environment values override values from the file, as dotenv users expect.
    values.update({key: value for key, value in os.environ.items() if key in values or key.startswith("VIDEO_") or key in {"SERIAL_PORT", "SERIAL_BAUD", "CONTROL_HOST", "CONTROL_PORT", "CUE_LEAD_MS"}})

    numbered: list[tuple[int, str]] = []
    for key, value in values.items():
        match = _VIDEO_KEY.fullmatch(key)
        if match:
            if not value.strip():
                raise ConfigError(f"{key} must not be blank")
            numbered.append((int(match.group(1)), value.strip()))
    if not numbered:
        raise ConfigError("No videos configured; add VIDEO_0=path/to/video.mp4 to .env")
    numbered.sort(key=lambda item: item[0])
    indices = [index for index, _ in numbered]
    if indices[0] != 0 or len(indices) != len(set(indices)):
        raise ConfigError("Video entries must have unique numeric indices starting at VIDEO_0")

    videos = tuple((root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve() for _, value in numbered)
    video_rgbs = []
    for index, _ in numbered:
        key = f"VIDEO_{index}_RGB"
        default = _RGB_DEFAULTS[index] if index < len(_RGB_DEFAULTS) else _RGB_DEFAULTS[-1]
        video_rgbs.append(_parse_rgb(key, values.get(key, ",".join(map(str, default)))))
    video_cues = []
    for index, _ in numbered:
        cues_value, clips_value = values.get(f"VIDEO_{index}_CUES", ""), values.get(f"VIDEO_{index}_CLIPS", "")
        if cues_value.strip() and clips_value.strip():
            raise ConfigError(f"Use either VIDEO_{index}_CLIPS or VIDEO_{index}_CUES, not both")
        if clips_value.strip():
            video_cues.append(_parse_clips(f"VIDEO_{index}_CLIPS", clips_value))
        else:
            video_cues.append(_parse_cues(f"VIDEO_{index}_CUES", cues_value))
    video_cues = tuple(video_cues)
    port = values.get("SERIAL_PORT", "").strip() or None
    try:
        baud = int(values.get("SERIAL_BAUD", "115200").strip())
        if baud <= 0:
            raise ValueError
    except ValueError as exc:
        raise ConfigError("SERIAL_BAUD must be a positive integer") from exc
    host = values.get("CONTROL_HOST", "").strip() or "127.0.0.1"
    try:
        control_port = int(values.get("CONTROL_PORT", "8080").strip() or "8080")
        if not 0 <= control_port <= 65535:
            raise ValueError
    except ValueError as exc:
        raise ConfigError("CONTROL_PORT must be an integer from 0 to 65535 (0 disables the control panel)") from exc
    try:
        cue_lead_ms = int(values.get("CUE_LEAD_MS", "0").strip() or "0")
        if not 0 <= cue_lead_ms <= 5000:
            raise ValueError
    except ValueError as exc:
        raise ConfigError("CUE_LEAD_MS must be an integer from 0 to 5000") from exc
    return Config(
        videos=videos,
        video_rgbs=tuple(video_rgbs),
        serial_port=port,
        serial_baud=baud,
        control_host=host,
        control_port=control_port,
        cue_lead_ms=cue_lead_ms,
        video_cues=video_cues,
    )
