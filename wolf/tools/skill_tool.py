"""Skill tool — Load and manage Wolf skills.

Skills are reusable procedural knowledge stored in ~/.wolf/skills/.
Compatible with Hermes SKILL.md and Claude Code skill formats.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from wolf.tools.registry import registry

logger = logging.getLogger(__name__)

SKILLS_DIR = Path.home() / ".wolf" / "skills"


def _load_skill_metadata(skill_path: Path) -> Optional[Dict[str, Any]]:
    """Load skill metadata from SKILL.md."""
    skill_file = skill_path / "SKILL.md" if skill_path.is_dir() else skill_path
    if not skill_file.exists():
        # Try as standalone .md file
        if skill_path.exists() and skill_path.suffix == ".md":
            skill_file = skill_path
        else:
            return None

    try:
        content = skill_file.read_text(encoding="utf-8")
        # Parse YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                meta["body"] = parts[2].strip()
                meta["path"] = str(skill_file)
                return meta
        # No frontmatter — treat entire file as content
        return {"name": skill_file.stem, "body": content, "path": str(skill_file)}
    except Exception as e:
        logger.warning(f"Failed to load skill {skill_path}: {e}")
        return None


def skill_list_handler(args: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    """List available skills."""
    skills = []
    if not SKILLS_DIR.exists():
        return {"skills": [], "message": "No skills directory found"}

    for item in sorted(SKILLS_DIR.rglob("*.md")):
        if item.name.startswith("."):
            continue
        meta = _load_skill_metadata(item)
        if meta:
            skills.append({
                "name": meta.get("name", item.stem),
                "description": meta.get("description", "")[:100],
                "path": str(item),
                "category": item.parent.name if item.parent != SKILLS_DIR else "",
            })

    # Also check for SKILL.md in subdirectories
    for item in sorted(SKILLS_DIR.rglob("SKILL.md")):
        meta = _load_skill_metadata(item.parent)
        if meta:
            name = meta.get("name", item.parent.name)
            if not any(s["name"] == name for s in skills):
                skills.append({
                    "name": name,
                    "description": meta.get("description", "")[:100],
                    "path": str(item),
                    "category": item.parent.parent.name if item.parent.parent != SKILLS_DIR else "",
                })

    return {"skills": skills, "total": len(skills)}


def skill_load_handler(args: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Load a skill by name or path."""
    name = args.get("name", "")
    if not name:
        return {"error": "No skill name provided"}

    # Try direct path
    direct = Path(os.path.expanduser(name))
    if direct.exists():
        meta = _load_skill_metadata(direct)
        if meta:
            return meta

    # Search by name
    if SKILLS_DIR.exists():
        for item in SKILLS_DIR.rglob("*.md"):
            if item.stem == name or item.stem == name.replace("-", "_"):
                meta = _load_skill_metadata(item)
                if meta:
                    return meta
        for item in SKILLS_DIR.rglob("SKILL.md"):
            if item.parent.name == name:
                meta = _load_skill_metadata(item.parent)
                if meta:
                    return meta

    return {"error": f"Skill not found: {name}"}


SKILL_SCHEMA = {
    "description": "Load skills (reusable knowledge). Use action=list to browse, action=load to get content.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "load"], "description": "Action to perform"},
            "name": {"type": "string", "description": "Skill name (for load action)"},
        },
        "required": ["action"],
    },
}


def skill_handler(args: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    action = args.get("action", "list")
    if action == "list":
        return skill_list_handler(args, context)
    elif action == "load":
        return skill_load_handler(args, context)
    return {"error": f"Unknown action: {action}"}


registry.register(
    name="skill", toolset="skills", schema=SKILL_SCHEMA,
    handler=skill_handler, emoji="📚",
)
