"""Agent Loader — Load agent definitions from ~/.wolf/agents/ and ~/.claude/agents/.

Compatible with Claude Code agent format:
    ---
    name: agent-name
    description: "Agent description"
    model: sonnet
    skills:
      - category/skill-name.md
    ---
    # Agent Name
    ## 角色定位
    ...
"""

import os
import yaml
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AGENT_DIRS = [
    Path.home() / ".wolf" / "agents",
    Path.home() / ".claude" / "agents",
]

SKILL_DIRS = [
    Path.home() / ".wolf" / "skills",
    Path.home() / ".claude" / "skills",
    Path.home() / ".hermes" / "skills",
]


@dataclass
class AgentDefinition:
    """A loaded agent definition."""
    name: str
    description: str = ""
    model: str = ""
    skills: List[str] = field(default_factory=list)
    body: str = ""  # Full markdown body (role, capabilities, workflow)
    path: str = ""
    # Resolved skill contents
    resolved_skills: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def system_prompt(self) -> str:
        """Build system prompt from agent definition + resolved skills."""
        parts = []

        # Agent body (role, capabilities, workflow)
        if self.body:
            parts.append(self.body)

        # Resolved skill contents
        for skill in self.resolved_skills:
            skill_body = skill.get("body", "")
            if skill_body:
                parts.append(f"## Loaded Skill: {skill.get('name', 'unknown')}\n\n{skill_body}")

        return "\n\n---\n\n".join(parts)


def load_all_agents() -> List[AgentDefinition]:
    """Load all agent definitions from all known directories."""
    agents = []
    seen_names = set()

    for agent_dir in AGENT_DIRS:
        if not agent_dir.exists():
            continue
        for md_file in sorted(agent_dir.glob("*.md")):
            agent = _parse_agent_file(md_file)
            if agent and agent.name not in seen_names:
                agents.append(agent)
                seen_names.add(agent.name)

    return agents


def load_agent(name: str) -> Optional[AgentDefinition]:
    """Load a specific agent by name."""
    for agent_dir in AGENT_DIRS:
        if not agent_dir.exists():
            continue
        # Try exact name
        for md_file in agent_dir.glob("*.md"):
            if md_file.stem == name:
                agent = _parse_agent_file(md_file)
                if agent:
                    _resolve_skills(agent)
                    return agent
    return None


def find_agent_for_task(task_description: str) -> Optional[AgentDefinition]:
    """Find the best agent for a task based on keyword matching."""
    agents = load_all_agents()
    if not agents:
        return None

    task_lower = task_description.lower()
    scored = []

    for agent in agents:
        score = 0
        name = agent.name.lower()
        desc = agent.description.lower()
        body = agent.body.lower()[:500]

        # Keyword matching
        keywords = {
            "rag": ["rag", "retrieval", "检索", "知识库", "向量", "milvus"],
            "agent-center": ["智能体中台", "agent center", "多agent", "会话管理"],
            "mcp": ["mcp", "model context protocol", "工具协议"],
            "a2a": ["a2a", "agent-to-agent", "多进程"],
            "spring-cloud": ["spring cloud", "微服务", "nacos", "gateway"],
            "spring-boot": ["spring boot", "单体", "crud"],
            "jeecgboot": ["jeecg", "积木", "online表单", "工作流"],
            "bert": ["bert", "微调", "意图分类", "sft"],
            "ragas": ["ragas", "评估", "evaluation"],
            "streamlit": ["streamlit", "聊天界面", "ui"],
            "ai-orchestration": ["langchain", "langgraph", "流程编排", "agent编排"],
            "claude-code-dev": ["claude code", "agent开发", "智能体开发"],
            "hermes-arch": ["hermes", "网关", "多平台"],
        }

        for key, words in keywords.items():
            if key in name:
                for word in words:
                    if word in task_lower:
                        score += 5

        # General description matching
        for word in task_lower.split():
            if len(word) >= 3:
                if word in desc:
                    score += 2
                if word in body:
                    score += 1

        if score > 0:
            scored.append((score, agent))

    if scored:
        scored.sort(key=lambda x: -x[0])
        best_agent = scored[0][1]
        _resolve_skills(best_agent)
        return best_agent

    return None


def _parse_agent_file(path: Path) -> Optional[AgentDefinition]:
    """Parse an agent markdown file."""
    try:
        content = path.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                return AgentDefinition(
                    name=meta.get("name", path.stem),
                    description=meta.get("description", ""),
                    model=meta.get("model", ""),
                    skills=meta.get("skills", []),
                    body=parts[2].strip(),
                    path=str(path),
                )
        # No frontmatter
        return AgentDefinition(
            name=path.stem,
            body=content,
            path=str(path),
        )
    except Exception as e:
        logger.warning(f"Failed to parse agent {path}: {e}")
        return None


def _resolve_skills(agent: AgentDefinition):
    """Resolve skill references to actual content."""
    for skill_ref in agent.skills:
        skill_content = _find_skill(skill_ref)
        if skill_content:
            agent.resolved_skills.append(skill_content)
        else:
            logger.debug(f"Skill not found: {skill_ref}")


def _find_skill(skill_ref: str) -> Optional[Dict[str, Any]]:
    """Find and load a skill by reference path."""
    for skill_dir in SKILL_DIRS:
        if not skill_dir.exists():
            continue

        # Try direct path
        direct = skill_dir / skill_ref
        if direct.exists():
            return _load_skill_file(direct)

        # Try basename match
        basename = Path(skill_ref).name
        for found in skill_dir.rglob(basename):
            return _load_skill_file(found)

        # Try stem match
        stem = Path(skill_ref).stem
        for found in skill_dir.rglob(f"{stem}.md"):
            return _load_skill_file(found)

    return None


def _load_skill_file(path: Path) -> Optional[Dict[str, Any]]:
    """Load a skill file."""
    try:
        content = path.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                meta["body"] = parts[2].strip()
                meta["path"] = str(path)
                return meta
        return {"name": path.stem, "body": content, "path": str(path)}
    except Exception as e:
        logger.debug(f"Failed to load skill {path}: {e}")
        return None
