"""Skill Trigger — Intelligently match and inject skills into the conversation.

Scans all available skills, matches against the current task/context,
and returns the most relevant skill contents for system prompt injection.
"""

import re
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# All known skill directories
SKILL_DIRS = [
    Path.home() / ".wolf" / "skills",
    Path.home() / ".claude" / "skills",
    Path.home() / ".hermes" / "skills",
]

# Cache
_skills_cache: Optional[List[Dict[str, Any]]] = None


def get_all_skills() -> List[Dict[str, Any]]:
    """Get all skills from all directories (cached)."""
    global _skills_cache
    if _skills_cache is not None:
        return _skills_cache

    skills = []
    seen = set()

    for base_dir in SKILL_DIRS:
        if not base_dir.exists():
            continue
        for md_file in sorted(base_dir.rglob("*.md")):
            if md_file.name.startswith(".") or md_file.name == "README.md":
                continue
            skill = _parse_skill(md_file, base_dir)
            if skill and skill["name"] not in seen:
                skills.append(skill)
                seen.add(skill["name"])

        # Also check SKILL.md in subdirectories
        for skill_md in sorted(base_dir.rglob("SKILL.md")):
            skill = _parse_skill(skill_md, base_dir)
            if skill:
                skill.setdefault("name", skill_md.parent.name)
                if skill["name"] not in seen:
                    skills.append(skill)
                    seen.add(skill["name"])

    _skills_cache = skills
    return skills


def search_skills(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Search skills by relevance to a query. Returns top_k matches."""
    skills = get_all_skills()
    if not skills:
        return []

    query_lower = query.lower()
    query_words = set(w for w in re.findall(r'\b\w{2,}\b', query_lower) if len(w) >= 2)

    # Chinese keywords mapping
    cn_keywords = {
        "rag": ["rag", "retrieval", "检索", "知识库", "向量", "milvus", "bm25"],
        "agent": ["agent", "智能体", "multi-agent", "多agent"],
        "微调": ["fine-tune", "finetune", "sft", "微调", "lora", "peft"],
        "微服务": ["microservice", "微服务", "spring cloud", "nacos", "gateway"],
        "mcp": ["mcp", "model context protocol", "工具协议"],
        "a2a": ["a2a", "agent-to-agent", "多进程"],
        "评估": ["evaluate", "评估", "ragas", "指标"],
        "编排": ["orchestration", "编排", "langgraph", "langchain", "workflow"],
        "部署": ["deploy", "部署", "docker", "k8s", "ci/cd"],
        "测试": ["test", "测试", "tdd", "pytest"],
        "jeecg": ["jeecg", "积木", "online表单", "代码生成"],
        "java": ["java", "spring", "mybatis", "jpa"],
        "python": ["python", "fastapi", "flask", "django"],
        "前端": ["frontend", "前端", "react", "vue", "streamlit"],
        "数据库": ["database", "数据库", "postgresql", "mysql", "redis"],
        "wms": ["wms", "仓储", "warehouse"],
        "git": ["git", "版本控制", "commit", "branch", "merge"],
        "配置": ["config", "配置", "环境", "部署", "上线"],
        "架构": ["architecture", "架构", "设计模式", "模式"],
        "hook": ["hook", "钩子", "生命周期", "回调"],
        "权限": ["permission", "权限", "安全", "认证"],
        "压缩": ["compress", "压缩", "上下文", "token", "context"],
    }

    scored: List[Tuple[float, Dict[str, Any]]] = []

    for skill in skills:
        score = 0.0
        name = skill.get("name", "").lower()
        desc = skill.get("description", "").lower()
        tags = " ".join(skill.get("tags", [])).lower() if skill.get("tags") else ""
        body = skill.get("body", "").lower()[:1000]
        # Also check explicit triggers field (from Claude skills format)
        triggers = skill.get("triggers", [])
        if isinstance(triggers, list):
            triggers_str = " ".join(str(t) for t in triggers).lower()
        else:
            triggers_str = str(triggers).lower()

        # Name match (highest weight)
        for word in query_words:
            if word in name:
                score += 5.0

        # Description match
        for word in query_words:
            if word in desc:
                score += 3.0

        # Tag match
        for word in query_words:
            if word in tags:
                score += 3.0

        # Triggers match (high weight — explicit triggers are very relevant)
        for word in query_words:
            if word in triggers_str:
                score += 4.0

        # Body match (lower weight)
        for word in query_words:
            if word in body:
                score += 1.0

        # Chinese keyword expansion
        for key, expansions in cn_keywords.items():
            if any(e in query_lower for e in expansions):
                combined = name + " " + desc + " " + tags + " " + triggers_str
                if any(e in combined for e in expansions):
                    score += 4.0

        # allowedTools match (if skill specifies tools that match query intent)
        allowed_tools = skill.get("allowedTools", [])
        tool_keywords = {
            "Read": ["读", "查看", "分析", "read"],
            "Edit": ["编辑", "修改", "改", "edit"],
            "Write": ["写", "创建", "write"],
            "Bash": ["执行", "运行", "命令", "bash", "shell"],
            "Grep": ["搜索", "查找", "grep", "search"],
        }
        for tool in allowed_tools:
            if tool in tool_keywords:
                for kw in tool_keywords[tool]:
                    if kw in query_lower:
                        score += 1.0

        if score > 0:
            scored.append((score, skill))

    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:top_k]]


def build_skills_context(skills: List[Dict[str, Any]], max_chars: int = 15000) -> str:
    """Build a skills context string for system prompt injection."""
    if not skills:
        return ""

    parts = []
    total_chars = 0

    for skill in skills:
        body = skill.get("body", "")
        if not body:
            continue
        name = skill.get("name", "unknown")
        entry = f"### Skill: {name}\n\n{body}"

        if total_chars + len(entry) > max_chars:
            # Truncate
            remaining = max_chars - total_chars
            if remaining > 200:
                parts.append(entry[:remaining] + "\n... [truncated]")
            break

        parts.append(entry)
        total_chars += len(entry)

    if not parts:
        return ""

    return "## Relevant Skills\n\n" + "\n\n---\n\n".join(parts)


def _parse_skill(path: Path, base_dir: Path) -> Optional[Dict[str, Any]]:
    """Parse a skill file."""
    try:
        content = path.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                meta["body"] = parts[2].strip()
                meta["path"] = str(path)
                meta.setdefault("name", path.stem)
                # Extract category from path
                try:
                    rel = path.relative_to(base_dir)
                    if len(rel.parts) > 1:
                        meta.setdefault("category", rel.parts[0])
                except ValueError:
                    pass
                return meta
        return {"name": path.stem, "body": content, "path": str(path)}
    except Exception:
        return None


def invalidate_cache():
    """Invalidate the skills cache (call after skills are added/removed)."""
    global _skills_cache
    _skills_cache = None
