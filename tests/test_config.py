from pathlib import Path

import pytest

from portrait_player.config import ConfigError, load_config


def test_playlist_is_ordered_by_numeric_suffix_and_supports_more_entries(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "VIDEO_2=third.mp4\nVIDEO_0=first.mp4\nVIDEO_1=second.mp4\nVIDEO_10=tenth.mp4\n",
        encoding="utf-8",
    )

    config = load_config(env_file, project_root=tmp_path)

    assert config.videos == tuple(
        tmp_path / name for name in ("first.mp4", "second.mp4", "third.mp4", "tenth.mp4")
    )


def test_relative_paths_resolve_from_project_root_not_env_file(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    env_folder = project / "config"
    env_folder.mkdir()
    env_file = env_folder / "settings.env"
    env_file.write_text("VIDEO_0=media/clip.mp4\n", encoding="utf-8")

    config = load_config(env_file, project_root=project)

    assert config.videos == (project / "media" / "clip.mp4",)


def test_serial_is_disabled_when_port_blank_and_defaults_to_9600(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("VIDEO_0=clip.mp4\nSERIAL_PORT= \n", encoding="utf-8")

    config = load_config(env_file, project_root=tmp_path)

    assert config.serial_port is None
    assert config.serial_baud == 9600


@pytest.mark.parametrize("contents", ["", "SERIAL_PORT=COM3\n", "VIDEO_0=\n", "VIDEO_1=one.mp4\n"])
def test_missing_or_invalid_playlist_config_is_rejected(tmp_path, contents):
    env_file = tmp_path / ".env"
    env_file.write_text(contents, encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(env_file, project_root=tmp_path)


def test_invalid_serial_baud_is_rejected(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("VIDEO_0=clip.mp4\nSERIAL_BAUD=fast\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(env_file, project_root=tmp_path)
