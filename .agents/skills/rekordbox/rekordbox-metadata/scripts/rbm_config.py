"""Configuration for rekordbox-metadata.

Reads a flat YAML-subset config file (key: value pairs plus simple `- item`
lists) so there is no PyYAML dependency. Credentials are NEVER stored here —
they come from environment variables or a local .env file (see load_env).
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_CONFIG = """\
# rekordbox-metadata configuration
music_directory: ~/Music
backup_directory: ~/Music/rekordbox-metadata-backups
review_directory: ~/Music/rekordbox-metadata-review
sources:
  - musicbrainz
  - discogs
default_write_mode: audio_tags
minimum_auto_confidence: 0.90
require_approval_for_existing_metadata: true
rekordbox_sync_mode: manual_reload_tag
"""

CONFIG_BASENAME = "rekordbox-metadata.yaml"


class ConfigError(Exception):
    pass


def parse_simple_yaml(text: str) -> dict:
    """Parse the flat key/value + simple-list YAML subset this skill uses."""
    out: dict = {}
    current_list_key = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            if current_list_key is None:
                raise ConfigError(f"list item outside a list: {raw!r}")
            out[current_list_key].append(_coerce(stripped[2:].strip()))
            continue
        if ":" not in stripped:
            raise ConfigError(f"unparseable config line: {raw!r}")
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            out[key] = []
            current_list_key = key
        else:
            out[key] = _coerce(value)
            current_list_key = None
    return out


def _coerce(value: str):
    v = value.strip().strip("'\"")
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no"):
        return False
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def config_search_paths() -> list[Path]:
    return [
        Path.cwd() / CONFIG_BASENAME,
        Path.home() / ".config" / CONFIG_BASENAME,
    ]


def find_config(explicit: str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.exists() else None
    for p in config_search_paths():
        if p.exists():
            return p
    return None


def create_default_config(path: Path | None = None) -> Path:
    path = path or config_search_paths()[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG)
    return path


def load_config(explicit: str | None = None) -> tuple[dict, Path]:
    path = find_config(explicit)
    if path is None:
        raise ConfigError(
            f"no config found (looked for {CONFIG_BASENAME} in cwd and ~/.config). "
            "Run the scan command once to create a default, then edit it."
        )
    cfg = parse_simple_yaml(path.read_text())
    for key in ("music_directory", "backup_directory", "review_directory"):
        if key not in cfg:
            raise ConfigError(f"config missing required key: {key}")
        cfg[key] = Path(str(cfg[key])).expanduser()
    cfg.setdefault("sources", ["musicbrainz", "discogs"])
    cfg.setdefault("minimum_auto_confidence", 0.90)
    cfg.setdefault("require_approval_for_existing_metadata", True)
    cfg.setdefault("rekordbox_sync_mode", "manual_reload_tag")
    return cfg, path


def load_env() -> dict:
    """Return credential values from the environment, falling back to a local
    .env file (cwd, then home). Values never leave this dict — callers must not
    print or log them."""
    creds = {}
    for name in ("DISCOGS_TOKEN", "DISCOGS_USER_TOKEN"):
        if os.environ.get(name):
            creds["discogs_token"] = os.environ[name]
            break
    if "discogs_token" not in creds:
        for envfile in (Path.cwd() / ".env", Path.home() / ".env"):
            if not envfile.exists():
                continue
            for line in envfile.read_text().splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() in ("DISCOGS_TOKEN", "DISCOGS_USER_TOKEN") and v.strip():
                    creds["discogs_token"] = v.strip().strip("'\"")
                    break
            if "discogs_token" in creds:
                break
    return creds
