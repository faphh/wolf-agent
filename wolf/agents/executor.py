"""Agent Executor — Run tasks with agent context.

When a task matches an agent, the executor:
1. Loads the agent definition
2. Resolves all referenced skills
3. Builds an enhanced system prompt
4. Runs the conversation loop with agent context
"""

import logging
from typing import Any, Dict, List, Optional

from wolf.agents.loader import AgentDefinition, load_agent, find_agent_for_task, load_all_agents
from wolf.providers.base import Message

logger = logging.getLogger(__name__)


class AgentExecutor:
    """Execute tasks with agent-specific context."""

    def __init__(self):
        self._agents_cache: Optional[List[AgentDefinition]] = None

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all available agents."""
        agents = self.get_agents()
        return [
            {
                "name": a.name,
                "description": a.description,
                "model": a.model,
                "skills_count": len(a.skills),
                "path": a.path,
            }
            for a in agents
        ]

    def get_agents(self) -> List[AgentDefinition]:
        if self._agents_cache is None:
            self._agents_cache = load_all_agents()
        return self._agents_cache

    def match_agent(self, task: str) -> Optional[AgentDefinition]:
        """Find the best matching agent for a task."""
        return find_agent_for_task(task)

    def get_agent_system_prompt(self, agent: AgentDefinition) -> str:
        """Build the complete system prompt for an agent."""
        parts = []

        # Core Wolf prompt
        parts.append(_WOLF_AGENT_PREFIX)

        # Agent-specific prompt (role + capabilities + workflow)
        if agent.body:
            parts.append(f"# Active Agent: {agent.name}\n\n{agent.body}")

        # Resolved skills
        if agent.resolved_skills:
            skill_parts = []
            for skill in agent.resolved_skills:
                skill_body = skill.get("body", "")
                if skill_body:
                    skill_parts.append(f"### {skill.get('name', 'Skill')}\n\n{skill_body}")
            if skill_parts:
                parts.append("## Loaded Skills\n\n" + "\n\n---\n\n".join(skill_parts))

        return "\n\n===\n\n".join(parts)


_WOLF_AGENT_PREFIX = """You are Wolf operating in Agent Mode.

You have been activated with a specialized agent definition that gives you deep
domain knowledge. Follow the agent's workflow and leverage the loaded skills.

## Rules
- Use your tools to actually implement solutions, don't just describe them.
- Follow the agent's workflow steps in order.
- Reference loaded skills for detailed templates and patterns.
- If a skill provides code templates, adapt them to the user's specific needs.
- After completing the task, consider if the approach is worth saving as a new skill.
"""


# Singleton
agent_executor = AgentExecutor()
