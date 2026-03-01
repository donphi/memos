# ============================================================================
# FILE: config_loader.py
# LOCATION: src/
# PIPELINE POSITION: Foundation - loaded before all other modules
# PURPOSE: Load paths.yaml + tuning.yaml, merge with env overrides, typed access
# ============================================================================
"""
ZERO hardcoded default values. If a value is missing from the YAML files
AND the env var is not set, it raises ConfigError with a clear message
telling you what to add and which file.

Config is split into two files:
  - config/paths.yaml   → every path, URL, directory, location
  - config/tuning.yaml  → every hyperparameter, threshold, timeout, model setting

ENV VAR OVERRIDES (secrets/deployment only):
- MEMOS_BASE_URL, MEMOS_API_TOKEN, CATEGORY_MEMO_UID
- DATABASE_URL, LLM_API_KEY, LLM_BASE_URL
- ROUTER_PORT, ROUTER_HOST
- LLM_CLASSIFY_ENABLED
"""

import os
import re
import yaml
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
PATHS_FILE = CONFIG_DIR / "paths.yaml"
TUNING_FILE = CONFIG_DIR / "tuning.yaml"
PROMPTS_DIR = CONFIG_DIR / "prompts"


class ConfigError(Exception):
    """Raised when a required config value is missing."""
    pass


class Config:
    """
    Typed config access with no hardcoded defaults.
    Every missing key raises ConfigError — fix it in the appropriate YAML file.
    """

    def __init__(self, paths_data: dict, tuning_data: dict):
        self._paths = paths_data
        self._tuning = tuning_data

    @classmethod
    def load(cls, paths_path: Optional[Path] = None,
             tuning_path: Optional[Path] = None) -> "Config":
        p_path = paths_path or PATHS_FILE
        t_path = tuning_path or TUNING_FILE

        if not p_path.exists():
            raise ConfigError(f"Paths config not found: {p_path}")
        if not t_path.exists():
            raise ConfigError(f"Tuning config not found: {t_path}")

        with open(p_path) as f:
            paths_data = yaml.safe_load(f) or {}
        with open(t_path) as f:
            tuning_data = yaml.safe_load(f) or {}

        required_paths_sections = ["memos", "database", "llm", "server", "data", "prompts", "git"]
        for section in required_paths_sections:
            if section not in paths_data:
                raise ConfigError(f"Missing required section '{section}' in {p_path}")

        required_tuning_sections = ["memos", "categories", "routing", "llm",
                                    "database", "events", "server", "web_ui", "debug"]
        for section in required_tuning_sections:
            if section not in tuning_data:
                raise ConfigError(f"Missing required section '{section}' in {t_path}")

        if "models" not in tuning_data["llm"]:
            raise ConfigError("Missing 'llm.models' section in tuning.yaml")

        # Env var overrides (secrets + deployment only)
        env_overrides_paths = {
            "MEMOS_BASE_URL": ("memos", "base_url"),
            "DATABASE_URL": ("database", "url"),
            "LLM_BASE_URL": ("llm", "base_url"),
        }
        for env_key, (section, key) in env_overrides_paths.items():
            val = os.environ.get(env_key)
            if val is not None:
                paths_data[section][key] = val

        env_overrides_tuning = {
            "MEMOS_API_TOKEN": ("memos", "api_token"),
            "CATEGORY_MEMO_UID": ("categories", "memo_uid"),
            "LLM_API_KEY": ("llm", "api_key"),
        }
        for env_key, (section, key) in env_overrides_tuning.items():
            val = os.environ.get(env_key)
            if val is not None:
                tuning_data[section][key] = val

        port_val = os.environ.get("ROUTER_PORT")
        if port_val is not None:
            paths_data["server"]["port"] = int(port_val)

        host_val = os.environ.get("ROUTER_HOST")
        if host_val is not None:
            paths_data["server"]["host"] = host_val

        llm_enabled = os.environ.get("LLM_CLASSIFY_ENABLED")
        if llm_enabled is not None:
            tuning_data["routing"]["enable_llm_fallback"] = llm_enabled.lower() == "true"

        instance = cls(paths_data, tuning_data)
        logger.info(f"Config loaded from {p_path} and {t_path}")
        return instance

    def _get_path(self, *keys):
        """Traverse paths config. Raises ConfigError on missing keys."""
        node = self._paths
        path_str = "paths." + ".".join(str(k) for k in keys)
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                raise ConfigError(
                    f"Missing config key: '{path_str}' — add it to config/paths.yaml"
                )
            node = node[key]
        return node

    def _get_tuning(self, *keys):
        """Traverse tuning config. Raises ConfigError on missing keys."""
        node = self._tuning
        path_str = "tuning." + ".".join(str(k) for k in keys)
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                raise ConfigError(
                    f"Missing config key: '{path_str}' — add it to config/tuning.yaml"
                )
            node = node[key]
        return node

    # ---- Memos (paths) ----
    @property
    def memos_base_url(self) -> str: return self._get_path("memos", "base_url")
    @property
    def memos_api_version(self) -> str: return self._get_path("memos", "api_version")
    @property
    def memos_webhook_url(self) -> str: return self._get_path("memos", "webhook_url")

    # ---- Memos (tuning) ----
    @property
    def memos_api_token(self) -> str: return self._get_tuning("memos", "api_token")
    @property
    def memos_request_timeout(self) -> float: return float(self._get_tuning("memos", "request_timeout_seconds"))

    # ---- Categories ----
    @property
    def category_memo_uid(self) -> str: return self._get_tuning("categories", "memo_uid")
    @property
    def tag_prefix(self) -> str: return self._get_tuning("categories", "tag_prefix")
    @property
    def default_category(self) -> str: return self._get_tuning("categories", "default_category")
    @property
    def sync_on_startup(self) -> bool: return self._get_tuning("categories", "sync_on_startup")

    # ---- Routing ----
    @property
    def enable_content_scan(self) -> bool: return self._get_tuning("routing", "enable_content_scan")
    @property
    def enable_llm_fallback(self) -> bool: return self._get_tuning("routing", "enable_llm_fallback")
    @property
    def ignore_tags(self) -> list[str]: return self._get_tuning("routing", "ignore_tags")

    # ---- LLM (paths) ----
    @property
    def llm_base_url(self) -> str: return self._get_path("llm", "base_url")

    # ---- LLM (tuning) ----
    @property
    def llm_provider(self) -> str: return self._get_tuning("llm", "provider")
    @property
    def llm_api_key(self) -> str: return self._get_tuning("llm", "api_key")
    @property
    def llm_request_timeout(self) -> float: return float(self._get_tuning("llm", "request_timeout_seconds"))
    @property
    def llm_max_retries(self) -> int: return int(self._get_tuning("llm", "max_retries"))
    @property
    def llm_extra_headers(self) -> dict: return self._get_tuning("llm", "extra_headers")
    @property
    def llm_anthropic_api_version(self) -> str: return self._get_tuning("llm", "anthropic_api_version")

    def llm_model_config(self, task: str) -> dict:
        models = self._get_tuning("llm", "models")
        if task not in models:
            raise ConfigError(
                f"No LLM model config for task '{task}'. "
                f"Available: {list(models.keys())}"
            )
        cfg = models[task]
        for k in ("id", "max_tokens", "temperature"):
            if k not in cfg:
                raise ConfigError(f"Missing 'llm.models.{task}.{k}' in tuning.yaml")
        return cfg

    # ---- Database (paths) ----
    @property
    def database_url(self) -> str: return self._get_path("database", "url")

    # ---- Database (tuning) ----
    @property
    def database_echo(self) -> bool: return self._get_tuning("database", "echo")

    # ---- Events (tuning) ----
    @property
    def preview_length(self) -> int: return int(self._get_tuning("events", "preview_length"))
    @property
    def diff_format(self) -> str: return self._get_tuning("events", "diff_format")
    @property
    def recent_memos_limit(self) -> int: return int(self._get_tuning("events", "recent_memos_limit"))
    @property
    def action_history_limit(self) -> int: return int(self._get_tuning("events", "action_history_limit"))

    # ---- Data directories (paths) ----
    @property
    def actions_dir(self) -> str: return self._get_path("data", "actions_dir")

    # ---- Server (paths) ----
    @property
    def server_host(self) -> str: return self._get_path("server", "host")
    @property
    def server_port(self) -> int: return int(self._get_path("server", "port"))

    # ---- Server (tuning) ----
    @property
    def server_log_level(self) -> str: return self._get_tuning("server", "log_level")
    @property
    def cors_origins(self) -> list[str]: return self._get_tuning("server", "cors_origins")

    # ---- Git identity (paths) ----
    @property
    def git_user_email(self) -> str: return self._get_path("git", "user_email")
    @property
    def git_user_name(self) -> str: return self._get_path("git", "user_name")

    # ---- Web UI (tuning) ----
    @property
    def dropdown_refresh_interval_ms(self) -> int: return int(self._get_tuning("web_ui", "dropdown_refresh_interval_ms"))
    @property
    def dropdown_poll_interval_ms(self) -> int: return int(self._get_tuning("web_ui", "dropdown_poll_interval_ms"))
    @property
    def mutation_observer_debounce_ms(self) -> int: return int(self._get_tuning("web_ui", "mutation_observer_debounce_ms"))

    # ---- Debug (tuning) ----
    @property
    def llm_response_preview_length(self) -> int: return int(self._get_tuning("debug", "llm_response_preview_length"))
    @property
    def llm_error_preview_length(self) -> int: return int(self._get_tuning("debug", "llm_error_preview_length"))

    # ---- Prompt loading ----

    def get_prompt(self, task: str, variables: dict) -> str:
        """
        Load config/prompts/{task}.txt, strip header above ---, inject {{variables}}.
        """
        prompts_dir = Path(self._get_path("prompts", "dir"))
        if not prompts_dir.is_absolute():
            prompts_dir = Path(__file__).resolve().parent.parent / prompts_dir

        prompt_path = prompts_dir / f"{task}.txt"
        if not prompt_path.exists():
            available = [p.stem for p in prompts_dir.glob("*.txt")]
            raise FileNotFoundError(
                f"Prompt not found: {prompt_path}. Available: {available}"
            )

        raw = prompt_path.read_text()

        if "---" in raw:
            parts = raw.split("---", 2)
            template = parts[-1].strip()
        else:
            template = raw.strip()

        for key, value in variables.items():
            template = template.replace("{{" + key + "}}", str(value))

        unresolved = re.findall(r"\{\{(\w+)\}\}", template)
        if unresolved:
            logger.warning(f"Prompt '{task}' has unresolved variables: {unresolved}")

        return template
