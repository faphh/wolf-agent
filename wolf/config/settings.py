"""Wolf Agent Configuration System.

Loads config from ~/.wolf/config.yaml and ~/.wolf/.env.
Merges defaults, file config, env vars, and CLI overrides.
"""

import os
import yaml
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

WOLF_HOME = Path.home() / ".wolf"
DEFAULT_CONFIG_PATH = WOLF_HOME / "config.yaml"
DEFAULT_ENV_PATH = WOLF_HOME / ".env"

DEFAULT_CONFIG: Dict[str, Any] = {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "fallback": [],
    "providers": {},
    "agent": {
        "max_iterations": 50,
        "max_retries": 3,
        "timeout": 300,
        "stream": True,
        "system_prompt_extra": "",
    },
    "tools": {
        "terminal": {
            "default_shell": "/bin/zsh",
            "timeout": 120,
        },
        "file": {
            "max_read_lines": 2000,
        },
    },
    "skills_dir": str(WOLF_HOME / "skills"),
    "agents_dir": str(WOLF_HOME / "agents"),
    "memory_dir": str(WOLF_HOME / "memory"),
    "ui": {
        "theme": "dark",
        "show_token_usage": True,
        "show_tool_calls": True,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base. Override wins."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider."""
    name: str
    api_key: str = ""
    base_url: str = ""
    api_type: str = "openai"  # "openai" | "anthropic" | "ollama"
    default_model: str = ""
    max_tokens: int = 8192
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WolfConfig:
    """Main Wolf configuration."""
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    fallback: List[Dict[str, str]] = field(default_factory=list)
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    agent: Dict[str, Any] = field(default_factory=lambda: DEFAULT_CONFIG["agent"].copy())
    tools: Dict[str, Any] = field(default_factory=lambda: DEFAULT_CONFIG["tools"].copy())
    skills_dir: str = str(WOLF_HOME / "skills")
    agents_dir: str = str(WOLF_HOME / "agents")
    memory_dir: str = str(WOLF_HOME / "memory")
    ui: Dict[str, Any] = field(default_factory=lambda: DEFAULT_CONFIG["ui"].copy())

    @property
    def skills_path(self) -> Path:
        return Path(os.path.expanduser(self.skills_dir))

    @property
    def agents_path(self) -> Path:
        return Path(os.path.expanduser(self.agents_dir))

    @property
    def memory_path(self) -> Path:
        return Path(os.path.expanduser(self.memory_dir))


def load_config(config_path: Optional[Path] = None) -> WolfConfig:
    """Load Wolf configuration from YAML + .env files."""
    config_path = config_path or DEFAULT_CONFIG_PATH

    # 1. Load .env into os.environ
    env_path = DEFAULT_ENV_PATH
    if env_path.exists():
        load_dotenv(env_path)

    # 2. Start with defaults
    raw = DEFAULT_CONFIG.copy()

    # 3. Merge config file
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = yaml.safe_load(f) or {}
            raw = _deep_merge(raw, file_config)
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")

    # 4. Build ProviderConfigs
    providers = {}
    # Known provider presets
    provider_presets = {
        "anthropic": {"api_type": "anthropic", "base_url": "https://api.anthropic.com"},
        "openai": {"api_type": "openai", "base_url": "https://api.openai.com/v1"},
        "xiaomi": {"api_type": "openai", "base_url": "https://token-plan-cn.xiaomimimo.com/v1"},
        "deepseek": {"api_type": "openai", "base_url": "https://api.deepseek.com/v1"},
        "ollama": {"api_type": "openai", "base_url": "http://localhost:11434/v1"},
    }

    for pname, pconf in raw.get("providers", {}).items():
        preset = provider_presets.get(pname, {})
        # Resolve API key: config > env var
        api_key = pconf.get("api_key", "") or os.environ.get(
            f"WOLF_{pname.upper()}_API_KEY",
            os.environ.get(f"{pname.upper()}_API_KEY", "")
        )
        providers[pname] = ProviderConfig(
            name=pname,
            api_key=api_key,
            base_url=pconf.get("base_url", preset.get("base_url", "")),
            api_type=pconf.get("api_type", preset.get("api_type", "openai")),
            default_model=pconf.get("model", ""),
            max_tokens=pconf.get("max_tokens", 8192),
        )

    # Auto-detect providers from env vars even if not in config
    for pname, preset in provider_presets.items():
        if pname not in providers:
            env_key = os.environ.get(f"WOLF_{pname.upper()}_API_KEY",
                                     os.environ.get(f"{pname.upper()}_API_KEY", ""))
            if env_key:
                providers[pname] = ProviderConfig(
                    name=pname,
                    api_key=env_key,
                    base_url=preset["base_url"],
                    api_type=preset["api_type"],
                )

    # Always ensure Anthropic is available if ANTHROPIC_API_KEY is set
    if "anthropic" not in providers:
        ak = os.environ.get("ANTHROPIC_API_KEY", "")
        if ak:
            providers["anthropic"] = ProviderConfig(
                name="anthropic", api_key=ak,
                base_url="https://api.anthropic.com", api_type="anthropic"
            )

    return WolfConfig(
        provider=raw.get("provider", "anthropic"),
        model=raw.get("model", "claude-sonnet-4-20250514"),
        fallback=raw.get("fallback", []),
        providers=providers,
        agent=raw.get("agent", DEFAULT_CONFIG["agent"]),
        tools=raw.get("tools", DEFAULT_CONFIG["tools"]),
        skills_dir=raw.get("skills_dir", str(WOLF_HOME / "skills")),
        agents_dir=raw.get("agents_dir", str(WOLF_HOME / "agents")),
        memory_dir=raw.get("memory_dir", str(WOLF_HOME / "memory")),
        ui=raw.get("ui", DEFAULT_CONFIG["ui"]),
    )


def ensure_wolf_dirs():
    """Create ~/.wolf directory structure."""
    for subdir in ["skills", "agents", "memory", "sessions"]:
        (WOLF_HOME / subdir).mkdir(parents=True, exist_ok=True)
    # Create default memory file
    memory_file = WOLF_HOME / "memory" / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text("# Wolf Agent Memory\n\n", encoding="utf-8")
    # Create default user profile
    user_file = WOLF_HOME / "memory" / "USER.md"
    if not user_file.exists():
        user_file.write_text("# User Profile\n\n", encoding="utf-8")
