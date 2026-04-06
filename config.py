"""
config.py — Load and validate config.yaml, deep-merge with defaults.

Usage:
    from config import load_config
    config = load_config()           # reads config.yaml next to this file
    config = load_config("my.yaml")  # reads a specific file
"""

import copy
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in defaults — every key the rest of the pipeline may reference.
# These mirror config.yaml exactly so a missing or partial user config still
# produces a fully valid config dict.
# ---------------------------------------------------------------------------
_DEFAULTS: dict = {
    "watch_folder": "~/Desktop/AudioDrop",
    "obsidian_vault_folder": "~/Documents/Obsidian/Inbox",
    "archive_folder": "~/Desktop/AudioDrop/processed",
    "transcriber": {
        "backend": "faster-whisper",
        "model": "base",
        "language": None,
        "device": "auto",
    },
    "llm": {
        "backend": "anthropic",
        "model": "claude-opus-4-6",
        "api_key_env": "ANTHROPIC_API_KEY",
    },
    "note": {
        "template_file": None,
        "fallback_tags": ["meeting", "notes", "audio"],
        "custom_prompt_instructions": "",
        "include_full_transcript": True,
        "collapse_transcript": True,
        "subfolder_pattern": "{year}/{month}",
    },
    "on_complete": {
        "audio_file_action": "archive",
    },
}

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------
_VALID_LLM_BACKENDS = {"anthropic", "openai", "ollama"}
_VALID_TRANSCRIBER_BACKENDS = {"faster-whisper", "openai-api"}
_VALID_AUDIO_ACTIONS = {"archive", "delete", "leave"}

# ---------------------------------------------------------------------------
# Path fields that should have ~ expanded to the user's home directory.
# Dot-separated keys for nested fields (e.g. "note.template_file").
# ---------------------------------------------------------------------------
_PATH_FIELDS: list[str] = [
    "watch_folder",
    "obsidian_vault_folder",
    "archive_folder",
    "note.template_file",
]


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge *override* into a copy of *base*.

    - Dict values are merged recursively so nested sections aren't clobbered.
    - All other value types (str, list, int, bool, None) in *override* win
      outright over the corresponding value in *base*.
    - Keys present only in *base* are preserved unchanged.
    """
    result = copy.deepcopy(base)
    for key, override_value in override.items():
        base_value = result.get(key)
        if isinstance(base_value, dict) and isinstance(override_value, dict):
            result[key] = _deep_merge(base_value, override_value)
        else:
            result[key] = copy.deepcopy(override_value)
    return result


def _expand_paths(config: dict) -> dict:
    """
    Expand ~ in every path field listed in _PATH_FIELDS.
    Operates on the config dict in-place and returns it for convenience.
    Skips fields whose value is None (e.g. optional template_file).
    """
    for dotted_key in _PATH_FIELDS:
        parts = dotted_key.split(".")
        # Walk to the parent dict
        parent = config
        for part in parts[:-1]:
            parent = parent.get(part, {})
            if not isinstance(parent, dict):
                break
        else:
            leaf_key = parts[-1]
            raw = parent.get(leaf_key)
            if raw is not None:
                parent[leaf_key] = str(Path(raw).expanduser())
    return config


def _validate(config: dict) -> None:
    """
    Validate critical config values and raise ValueError with a clear,
    actionable message if anything is wrong.
    """
    llm_backend = config.get("llm", {}).get("backend", "")
    if llm_backend not in _VALID_LLM_BACKENDS:
        raise ValueError(
            f"config.yaml: llm.backend '{llm_backend}' is not valid. "
            f"Must be one of: {', '.join(sorted(_VALID_LLM_BACKENDS))}"
        )

    transcriber_backend = config.get("transcriber", {}).get("backend", "")
    if transcriber_backend not in _VALID_TRANSCRIBER_BACKENDS:
        raise ValueError(
            f"config.yaml: transcriber.backend '{transcriber_backend}' is not valid. "
            f"Must be one of: {', '.join(sorted(_VALID_TRANSCRIBER_BACKENDS))}"
        )

    audio_action = config.get("on_complete", {}).get("audio_file_action", "")
    if audio_action not in _VALID_AUDIO_ACTIONS:
        raise ValueError(
            f"config.yaml: on_complete.audio_file_action '{audio_action}' is not valid. "
            f"Must be one of: {', '.join(sorted(_VALID_AUDIO_ACTIONS))}"
        )


def load_config(config_path: str | Path = "config.yaml") -> dict:
    """
    Load user config from *config_path*, deep-merge with built-in defaults,
    expand home-directory tildes in path fields, validate, and return the
    resulting config dict.

    Args:
        config_path: Path to the YAML config file. Relative paths are resolved
                     from the current working directory. Defaults to "config.yaml".

    Returns:
        A fully populated config dict ready for use by pipeline modules.

    Raises:
        FileNotFoundError: If *config_path* does not exist.
        yaml.YAMLError: If the YAML is malformed.
        ValueError: If a required config value is invalid.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path.resolve()}. "
            "Copy config.yaml from the project root and edit it."
        )

    logger.debug("Loading config from %s", path.resolve())

    with path.open("r", encoding="utf-8") as fh:
        user_config: dict = yaml.safe_load(fh) or {}

    if not isinstance(user_config, dict):
        raise ValueError(
            f"config.yaml must be a YAML mapping at the top level, "
            f"got {type(user_config).__name__}"
        )

    config = _deep_merge(_DEFAULTS, user_config)
    _expand_paths(config)
    _validate(config)

    logger.debug(
        "Config loaded. LLM backend=%s, transcriber backend=%s",
        config["llm"]["backend"],
        config["transcriber"]["backend"],
    )

    return config
