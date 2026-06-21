"""Skills Loader — Load skills from ~/.wolf/skills/ and project directories.

Compatible with both Hermes SKILL.md format and Claude Code .md format.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

WOLF_SKILLS_DIR = Path.home() / ".wolf" / "skills"
CLAUDE_SKILLS_DIR = Path.home() / ".claude" / "skills"
CLAUDE_AGENTS_DIR = Path.home() / ".claude" / "agents"
HERMES_SKILLS_DIR = Path.home() / ".hermes" / "skills"


def load_all_skills() -> List[Dict[str, Any]]:
    """Load skills from all known directories."""
    skills = []
    for base_dir in [WOLF_SKILLS_DIR, CLAUDE_SKILLS_DIR, HERMES_SKILLS_DIR]:
        if base_dir.exists():
            skills.extend(_scan_skills_dir(base_dir))
    return skills


def load_all_agents() -> List[Dict[str, Any]]:
    """Load agent definitions from all known directories."""
    agents = []
    for base_dir in [Path.home() / ".wolf" / "agents", CLAUDE_AGENTS_DIR]:
        if base_dir.exists():
            for f in base_dir.glob("*.md"):
                agent = _parse_md_file(f)
                if agent:
                    agents.append(agent)
    return agents


def _scan_skills_dir(base_dir: Path) -> List[Dict[str, Any]]:
    """Scan a directory for skills."""
    skills = []
    for item in sorted(base_dir.rglob("*.md")):
        if item.name.startswith(".") or item.name == "README.md":
            continue
        skill = _parse_md_file(item)
        if skill:
            skill.setdefault("category", _get_category(item, base_dir))
            skills.append(skill)
    for item in sorted(base_dir.rglob("SKILL.md")):
        skill = _parse_md_file(item)
        if skill:
            skill.setdefault("name", item.parent.name)
            skill.setdefault("category", _get_category(item.parent, base_dir))
            skill["path"] = str(item)
            skills.append(skill)
    return skills


def _parse_md_file(path: Path) -> Optional[Dict[str, Any]]:
    """Parse a markdown file with optional YAML frontmatter."""
    try:
        content = path.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                meta["body"] = parts[2].strip()
                meta["path"] = str(path)
                meta.setdefault("name", path.stem)
                return meta
        # No frontmatter
        return {"name": path.stem, "body": content, "path": str(path)}
    except Exception as e:
        logger.debug(f"Failed to parse {path}: {e}")
        return None


def _get_category(path: Path, base_dir: Path) -> str:
    """Extract category from relative path."""
    try:
        rel = path.relative_to(base_dir)
        if len(rel.parts) > 1:
            return rel.parts[0]
    except ValueError:
        pass
    return ""


def find_relevant_skills(query: str, skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Find skills relevant to a query using keyword matching."""
    query_lower = query.lower()
    scored = []
    for skill in skills:
        score = 0
        name = skill.get("name", "").lower()
        desc = skill.get("description", "").lower()
        body = skill.get("body", "").lower()[:500]
        tags = " ".join(skill.get("tags", [])).lower() if skill.get("tags") else ""

        for word in query_lower.split():
            if len(word) < 3:
                continue
            if word in name:
                score += 3
            if word in desc:
                score += 2
            if word in tags:
                score += 2
            if word in body:
                score += 1

        if score > 0:
            scored.append((score, skill))

    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:5]]
