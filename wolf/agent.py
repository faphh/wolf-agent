"""Wolf Agent — Main agent class that ties everything together."""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from wolf.config.settings import WolfConfig, load_config, ensure_wolf_dirs
from wolf.conversation_loop import ConversationLoop
from wolf.providers.base import Provider, create_provider
from wolf.tools.registry import registry

logger = logging.getLogger(__name__)

# Version
__version__ = "0.1.0"

# Core system prompt
WOLF_SYSTEM_PROMPT = """You are Wolf, a powerful AI assistant created to help with any task.

## Core Capabilities
- **Coding**: You are a top-tier programmer. Write, edit, debug, and refactor code with precision.
- **Terminal**: Execute shell commands, manage processes, interact with the system.
- **File Operations**: Read, write, edit, and search files efficiently.
- **Web Research**: Search the web and fetch content from URLs.
- **Memory**: You remember important facts across sessions.
- **Skills**: You have reusable knowledge skills that get loaded when relevant.

## Working Style
- Be direct and efficient. No unnecessary verbosity.
- For coding tasks, write production-quality code directly.
- Use tools proactively — don't just describe what to do, do it.
- When editing files, use the `patch` tool for precise changes.
- For complex multi-file tasks, use `execute_code` for batch operations.
- If a task is ambiguous, ask for clarification instead of guessing.

## Self-Evolution
- After completing complex tasks, consider saving your approach as a skill for future reuse.
- Learn from user feedback and update your memory accordingly.
- Continuously improve your procedural knowledge.

## Important
- Never fabricate information. If unsure, say so.
- For long-running tasks, use background processes.
- Always verify your work — read back files after editing, run tests after writing code.
"""


class WolfAgent:
    """The main Wolf agent."""

    def __init__(self, config: Optional[WolfConfig] = None):
        ensure_wolf_dirs()
        self.config = config or load_config()
        self._init_provider()
        self._init_tools()
        self._init_agents()
        self._load_memory()
        self.session_id = str(int(time.time()))
        self.conversation_count = 0
        self.active_agent = None  # Currently active agent definition

    def _init_provider(self):
        """Initialize the LLM provider."""
        self.provider = create_provider(
            self.config.provider,
            {"api_key": self._get_api_key(self.config.provider),
             "base_url": self._get_base_url(self.config.provider),
             "default_model": self.config.model,
             "max_tokens": 8192},
        )
        self.model = self.config.model

        # Build fallback chain
        self.fallback_providers: List[tuple] = []
        for fb in self.config.fallback:
            pname = fb.get("provider", "")
            pmodel = fb.get("model", "")
            if pname:
                try:
                    p = create_provider(pname, {
                        "api_key": self._get_api_key(pname),
                        "base_url": self._get_base_url(pname),
                        "default_model": pmodel,
                    })
                    self.fallback_providers.append((p, pmodel))
                except Exception as e:
                    logger.warning(f"Failed to init fallback provider {pname}: {e}")

    def _get_api_key(self, provider_name: str) -> str:
        pcfg = self.config.providers.get(provider_name)
        if pcfg:
            return pcfg.api_key
        return os.environ.get(f"{provider_name.upper()}_API_KEY",
                              os.environ.get(f"WOLF_{provider_name.upper()}_API_KEY", ""))

    def _get_base_url(self, provider_name: str) -> str:
        pcfg = self.config.providers.get(provider_name)
        if pcfg:
            return pcfg.base_url
        return ""

    def _init_tools(self):
        """Discover and load built-in tools."""
        from wolf.tools.registry import discover_builtin_tools
        discovered = discover_builtin_tools()
        logger.info(f"Loaded {len(discovered)} tool modules")

    def _init_agents(self):
        """Initialize the agent executor."""
        from wolf.agents.executor import agent_executor
        self.agent_executor = agent_executor
        agents = self.agent_executor.get_agents()
        logger.info(f"Loaded {len(agents)} agent definitions")

    def _load_memory(self):
        """Load memory context for system prompt."""
        memory_path = self.config.memory_path
        self.memory_context = ""

        memory_file = memory_path / "MEMORY.md"
        if memory_file.exists():
            content = memory_file.read_text(encoding="utf-8").strip()
            if content and content != "# Wolf Agent Memory":
                self.memory_context += f"\n\n## Agent Memory\n{content}"

        user_file = memory_path / "USER.md"
        if user_file.exists():
            content = user_file.read_text(encoding="utf-8").strip()
            if content and content != "# User Profile":
                self.memory_context += f"\n\n## User Profile\n{content}"

    def _load_skills_context(self, query: str = "") -> str:
        """Load relevant skills based on query context."""
        from wolf.skills.trigger import search_skills, build_skills_context

        if not query:
            # No query context — just load project-level context
            return self._load_project_context()

        # Smart skill search
        relevant_skills = search_skills(query, top_k=3)
        if relevant_skills:
            return build_skills_context(relevant_skills, max_chars=12000)
        return self._load_project_context()

    def _load_project_context(self) -> str:
        """Load project-level context files (CLAUDE.md, AGENTS.md, WOLF.md)."""
        cwd = os.getcwd()
        context_parts = []
        for fname in ["CLAUDE.md", "AGENTS.md", "WOLF.md"]:
            fpath = Path(cwd) / fname
            if fpath.exists():
                content = fpath.read_text(encoding="utf-8").strip()
                if content:
                    context_parts.append(f"## Project Context ({fname})\n{content}")
        return "\n\n".join(context_parts)

    def _build_system_prompt(self, user_message: str = "") -> str:
        """Build the complete system prompt."""
        # If an agent is active, use agent-specific prompt
        if self.active_agent:
            parts = [self.agent_executor.get_agent_system_prompt(self.active_agent)]
        else:
            parts = [WOLF_SYSTEM_PROMPT]

        if self.memory_context:
            parts.append(self.memory_context)

        # Smart skill injection based on user message
        skills_ctx = self._load_skills_context(user_message)
        if skills_ctx:
            parts.append(skills_ctx)

        extra = self.config.agent.get("system_prompt_extra", "")
        if extra:
            parts.append(extra)

        return "\n\n---\n\n".join(parts)

    def chat(self, user_message: str, callback=None) -> str:
        """Process a user message and return the response.

        Args:
            user_message: The user's input
            callback: Optional streaming callback

        Returns:
            The assistant's response
        """
        # Auto-detect agent if none active
        if self.active_agent is None:
            matched = self.agent_executor.match_agent(user_message)
            if matched:
                self.active_agent = matched
                logger.info(f"Auto-matched agent: {matched.name}")

        loop = ConversationLoop(
            provider=self.provider,
            model=self.model,
            config=self.config.agent,
            fallback_providers=self.fallback_providers,
        )

        system_prompt = self._build_system_prompt(user_message)
        response = loop.run(user_message, system_prompt=system_prompt, callback=callback)

        self.conversation_count += 1
        logger.debug(f"Turn {self.conversation_count}: {loop.get_usage_summary()}")

        return response

    def set_agent(self, agent_name: str) -> str:
        """Activate a specific agent by name."""
        from wolf.agents.loader import load_agent
        if agent_name == "none" or agent_name == "off":
            self.active_agent = None
            return "Agent mode deactivated. Using default Wolf."
        agent = load_agent(agent_name)
        if agent:
            self.active_agent = agent
            return f"Agent activated: {agent.name} — {agent.description}"
        return f"Agent not found: {agent_name}"

    def list_agents(self) -> list:
        return self.agent_executor.list_agents()

    def get_toolsets(self) -> List[str]:
        """Get available toolset names."""
        return ["terminal", "file", "web", "memory", "skills", "task"]
