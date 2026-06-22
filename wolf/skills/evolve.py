"""Self-Evolution Engine — Auto-extract skills from successful patterns.

After completing complex tasks (5+ tool calls, no errors in last 3),
Wolf analyzes the conversation and extracts reusable patterns as new skills.

Triggered automatically after each conversation turn in the agent.
"""

import os
import re
import yaml
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from wolf.skills.score import record_skill_use, get_skill_score, get_low_quality_skills

logger = logging.getLogger(__name__)

SKILLS_DIR = Path.home() / ".wolf" / "skills"


def analyze_conversation(messages: List[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    """Analyze a completed conversation and decide if it should become a skill.

    Returns:
        None if no skill should be created, or dict with:
        {"name": "...", "description": "...", "steps": [...], "tools": [...]}
    """
    if len(messages) < 6:
        return None

    # Extract tool usage sequence
    tool_calls = []
    tool_results = []
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tool_calls.append(tc.get("name", "unknown"))
        elif msg.get("role") == "tool":
            tool_results.append(msg.get("content", ""))

    if len(tool_calls) < 5:
        return None

    # Check for errors in last 3 tool results
    if tool_results:
        recent_results = tool_results[-3:]
        error_count = sum(1 for r in recent_results if isinstance(r, str) and "error" in r.lower())
        if error_count >= 2:
            return None  # Too many errors, don't extract

    # Check if the pattern is meaningful
    unique_tools = list(dict.fromkeys(tool_calls))  # Preserves order, removes dupes
    if len(unique_tools) < 2:
        return None

    # Extract task description from first user message
    task_desc = ""
    for msg in messages:
        if msg.get("role") == "user":
            task_desc = msg.get("content", "")
            break

    # Generate skill metadata
    skill_name = _generate_skill_name(task_desc, unique_tools)
    if not skill_name:
        return None

    # Build step descriptions
    steps = _extract_steps(messages, tool_calls)

    # Check if similar skill already exists
    if _skill_exists(skill_name):
        return None

    return {
        "name": skill_name,
        "description": f"Auto-extracted: {task_desc[:80]}",
        "tools": unique_tools,
        "steps": steps,
        "task_hint": task_desc[:200],
    }


def create_skill(skill_data: Dict[str, Any]) -> str:
    """Create a new skill file from extracted data."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    name = skill_data["name"]
    skill_dir = SKILLS_DIR / "auto-extracted" / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    tools = skill_data.get("tools", [])
    steps = skill_data.get("steps", [])
    desc = skill_data.get("description", "")
    task_hint = skill_data.get("task_hint", "")

    # Build SKILL.md content
    steps_md = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) if steps else "1. Analyze the task\n2. Execute tools in order\n3. Verify results"
    tools_str = ", ".join(tools[:8])

    content = f"""---
name: {name}
description: "{desc}"
tags: [auto-extracted, programming]
tools_used: [{tools_str}]
created: {time.strftime("%Y-%m-%d")}
---

# {name}

{desc}

## When to Use
- When the task involves: {task_hint[:100]}
- Tools typically used: {tools_str}

## Steps

{steps_md}

## Notes
This skill was auto-extracted from a successful conversation.
Review and refine it for better reusability.
"""

    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")
    logger.info(f"Auto-extracted skill: {name} at {skill_file}")
    return str(skill_file)


def try_evolve(messages: list) -> Optional[str]:
    """Main entry point: analyze and potentially create a skill.

    Args:
        messages: List of Message objects from the conversation

    Returns:
        Skill path if created, None otherwise
    """
    # Convert Message objects to dicts
    msg_dicts = []
    for msg in messages:
        if hasattr(msg, '__dict__'):
            d = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                d["tool_calls"] = msg.tool_calls
            msg_dicts.append(d)
        elif isinstance(msg, dict):
            msg_dicts.append(msg)

    skill_data = analyze_conversation(msg_dicts)
    if skill_data:
        return create_skill(skill_data)
    return None


def _generate_skill_name(task_desc: str, tools: List[str]) -> Optional[str]:
    """Generate a skill name from task description and tools used."""
    # Extract key words from task
    words = re.findall(r'[a-z]{3,}', task_desc.lower())
    stop_words = {"the", "and", "for", "that", "this", "with", "from", "have", "are",
                  "was", "were", "been", "will", "would", "could", "should", "can",
                  "just", "like", "know", "make", "help", "need", "want", "please",
                  "using", "write", "create", "make"}

    key_words = [w for w in words if w not in stop_words][:3]
    if not key_words:
        return None

    name = "-".join(key_words)
    # Cap at 40 chars
    if len(name) > 40:
        name = name[:40]

    return name


def _extract_steps(messages: List[Dict], tool_calls: List[str]) -> List[str]:
    """Extract high-level steps from the conversation."""
    steps = []
    seen_tools = set()

    for tc_name in tool_calls:
        if tc_name not in seen_tools:
            seen_tools.add(tc_name)
            step_desc = _tool_to_step(tc_name)
            if step_desc:
                steps.append(step_desc)

    return steps[:10]  # Max 10 steps


def _tool_to_step(tool_name: str) -> Optional[str]:
    """Convert a tool name to a human-readable step description."""
    mapping = {
        "read_file": "Read and analyze the relevant files",
        "write_file": "Create/overwrite the target file",
        "patch": "Make precise edits to the file",
        "search_files": "Search for relevant code/content",
        "terminal": "Execute shell commands",
        "execute_code": "Run Python code for batch operations",
        "web_search": "Search the web for reference information",
        "web_fetch": "Fetch web content for reference",
        "git_status": "Check git working tree status",
        "git_diff": "Review file changes",
        "git_commit": "Commit the changes",
        "git_log": "Review commit history",
        "memory": "Update persistent memory",
    }
    return mapping.get(tool_name)


def refine_skill(skill_name: str, feedback: str, success: bool) -> Optional[str]:
    """Refine an existing skill based on feedback.

    When a skill is used and fails, this function can update the skill
    with the feedback to improve future performance.
    """
    # Record the usage
    record_skill_use(skill_name, success, context=feedback)

    # Check if skill needs improvement
    score = get_skill_score(skill_name)
    if score["status"] in ("poor", "needs_review") and score["uses"] >= 5:
        # Find the skill file
        skill_file = _find_skill_file(skill_name)
        if not skill_file:
            return None

        try:
            content = skill_file.read_text(encoding="utf-8")
            # Append feedback as a lessons-learned section
            if "## Lessons Learned" not in content:
                content += f"\n\n## Lessons Learned\n- [{_timestamp()}] {feedback[:200]}\n"
            else:
                # Append to existing section
                content = content.replace(
                    "## Lessons Learned",
                    f"## Lessons Learned\n- [{_timestamp()}] {feedback[:200]}",
                )
            skill_file.write_text(content, encoding="utf-8")
            logger.info(f"Refined skill {skill_name} with feedback")
            return str(skill_file)
        except Exception as e:
            logger.error(f"Failed to refine skill: {e}")

    return None


def _find_skill_file(name: str) -> Optional[Path]:
    """Find a skill file by name."""
    for base in [SKILLS_DIR, Path.home() / ".claude" / "skills", Path.home() / ".hermes" / "skills"]:
        if not base.exists():
            continue
        for f in base.rglob("SKILL.md"):
            if f.parent.name == name:
                return f
        for f in base.rglob(f"{name}.md"):
            return f
    return None


def _timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


def _skill_exists(name: str) -> bool:
    """Check if a skill with this name already exists."""
    for subdir in ["auto-extracted", ""]:
        check_dir = SKILLS_DIR / subdir if subdir else SKILLS_DIR
        if check_dir.exists():
            for skill_file in check_dir.rglob("SKILL.md"):
                if skill_file.parent.name == name:
                    return True
    return False
