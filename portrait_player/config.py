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
    serial_port: str | None = None
    serial_baud: int = 9600


_VIDEO_KEY = re.compile(r"^VIDEO_(\d+)$")


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
    port = values.get("SERIAL_PORT", "").strip() or None
    try:
        baud = int(values.get("SERIAL_BAUD", "9600").strip())
        if baud <= 0:
            raise ValueError
    except ValueError as exc:
        raise ConfigError("SERIAL_BAUD must be a positive integer") from exc
    return Config(videos=videos, serial_port=port, serial_baud=baud)
