"""Configuration loading and validation."""

from dataclasses import dataclass
import os
from pathlib import Path
import re


class ConfigError(ValueError):
    """Raised when the player configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    videos: tuple[Path, ...]
    video_rgbs: tuple[tuple[int, int, int], ...]
    serial_port: str | None = None
    serial_baud: int = 115200


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
    values.update({key: value for key, value in os.environ.items() if key in values or key.startswith("VIDEO_") or key in {"SERIAL_PORT", "SERIAL_BAUD"}})

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
    port = values.get("SERIAL_PORT", "").strip() or None
    try:
        baud = int(values.get("SERIAL_BAUD", "115200").strip())
        if baud <= 0:
            raise ValueError
    except ValueError as exc:
        raise ConfigError("SERIAL_BAUD must be a positive integer") from exc
    return Config(videos=videos, video_rgbs=tuple(video_rgbs), serial_port=port, serial_baud=baud)
