"""Shared bash configuration loader for Python backends."""
import json
import os
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "provider": "openai",
    "baseURL": "http://localhost:8080/v1",
    "apiKey": "sk-fallback",
    "model": "gpt-4",
    "allowList": [],
    "allowAll": True,
}


def load_chatlets_config() -> dict[str, Any]:
    """Walk up the directory tree to find config/config.json."""
    dir = os.getcwd()
    root = "/"
    while dir != root:
        config_path = os.path.join(dir, "config", "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    parsed = json.load(f)
                return {**DEFAULT_CONFIG, **parsed}
            except (json.JSONDecodeError, OSError):
                return dict(DEFAULT_CONFIG)
        dir = os.path.dirname(dir)
    return dict(DEFAULT_CONFIG)


def get_bash_commands_prompt(config: dict[str, Any]) -> str:
    """Generate dynamic bash commands prompt string."""
    if config.get("allowAll", True):
        return "You can execute any shell command via the bash tool."
    allow_list = config.get("allowList", [])
    if not allow_list:
        return "You can execute no shell commands via the bash tool."
    return f"You can execute these shell commands: {', '.join(allow_list)}"
