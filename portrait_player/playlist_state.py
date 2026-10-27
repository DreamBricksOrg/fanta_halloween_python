"""Persist the on-demand playlist (order, paths, colors) across restarts."""

from __future__ import annotations

import json
from pathlib import Path

from .playback import check_rgb, parse_cues

STATE_FILE = "playlist_state.json"


def load_state(path: Path):
    """Return (videos, rgbs, cues) saved earlier, or None when absent or unusable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data["videos"]
        videos = tuple(Path(item["path"]) for item in items)
        rgbs = tuple(check_rgb(item["rgb"]) for item in items)
        cues = tuple(parse_cues(item.get("cues", [])) for item in items)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return (videos, rgbs, cues) if videos else None


def save_state(path: Path, player) -> None:
    data = {
        "videos": [
            {"path": str(v), "rgb": list(c), "cues": [{"t": t / 1000, "rgb": list(rgb)} for t, rgb in cues]}
            for v, c, cues in zip(player.videos, player.video_rgbs, player.video_cues)
        ]
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)
