"""Wolf System Prompt Builder — Dynamic, context-aware prompt generation.

Builds a comprehensive system prompt that includes:
- Role definition and personality
- Tool strategy (when to use which tool)
- Agent routing guidance
- Skill trigger awareness
- Permission system awareness
- Context compression awareness
- Self-evolution guidance
- Project context
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def build_system_prompt(
    memory_context: str = "",
    skills_context: str = "",
    project_context: str = "",
    active_agent=None,
    tool_names: List[str] = None,
    agent_names: List[str] = None,
) -> str:
    """Build the complete Wolf system prompt dynamically."""

    parts = []

    # ── Core Identity ────────────────────────────────────────────
    parts.append(_IDENTITY)

    # ── Tool Strategy ────────────────────────────────────────────
    if tool_names:
        parts.append(_build_tool_strategy(tool_names))

    # ── Agent Routing ────────────────────────────────────────────
    if agent_names:
        parts.append(_build_agent_routing(agent_names))

    # ── Active Agent Context ─────────────────────────────────────
    if active_agent:
        parts.append(f"""## Active Agent: {active_agent.name}

You are currently operating as **{active_agent.name}**.
{active_agent.description}

Follow the agent's workflow and leverage loaded skills for detailed templates.""")

    # ── Skill Awareness ──────────────────────────────────────────
    parts.append(_SKILL_AWARENESS)

    # ── Permission Awareness ─────────────────────────────────────
    parts.append(_PERMISSION_AWARENESS)

    # ── Context Management ───────────────────────────────────────
    parts.append(_CONTEXT_MANAGEMENT)

    # ── Self-Evolution ───────────────────────────────────────────
    parts.append(_SELF_EVOLUTION)

    # ── Working Style ────────────────────────────────────────────
    parts.append(_WORKING_STYLE)

    # ── Injected Contexts ────────────────────────────────────────
    if memory_context:
        parts.append(memory_context)

    if skills_context:
        parts.append(skills_context)

    if project_context:
        parts.append(project_context)

    return "\n\n---\n\n".join(parts)


# ── Prompt Sections ──────────────────────────────────────────────

_IDENTITY = """You are Wolf, a powerful AI agent with top-tier coding capabilities and broad general knowledge.

You combine the versatility of a general-purpose assistant with the precision of a senior programmer. You don't just describe solutions — you implement them directly using your tools."""


def _build_tool_strategy(tool_names: List[str]) -> str:
    """Build tool selection strategy based on available tools."""
    sections = ["## Tool Selection Strategy\n"]

    # Group tools by category
    categories = {
        "File Operations": [],
        "Code Execution": [],
        "Git": [],
        "Web": [],
        "Knowledge": [],
        "Coding Deep": [],
    }

    for name in tool_names:
        if name in ("read_file", "write_file", "patch", "search_files", "notebook_read", "notebook_edit", "notebook_create"):
            categories["File Operations"].append(name)
        elif name in ("terminal", "execute_code"):
            categories["Code Execution"].append(name)
        elif name.startswith("git_"):
            categories["Git"].append(name)
        elif name in ("web_search", "web_fetch"):
            categories["Web"].append(name)
        elif name in ("memory", "skill", "todo"):
            categories["Knowledge"].append(name)
        elif name in ("diagnostics", "run_tests", "refactor"):
            categories["Coding Deep"].append(name)

    strategies = {
        "File Operations": """**Reading files**: Use `read_file` (with offset/limit for large files). For finding files by name: `search_files` with target="files". For finding content: `search_files` with target="content".

**Writing files**: Use `write_file` to create/overwrite. Use `patch` for precise edits (preferred for modifications — it uses fuzzy matching).

**Jupyter notebooks**: Use `notebook_read`/`notebook_edit`/`notebook_create` for .ipynb files.

**Multi-file refactoring**: Use `refactor` for find-replace across files. Always preview first (default), then apply with preview=false.""",

        "Code Execution": """**Simple commands**: Use `terminal` for shell commands. Read-only commands (ls, cat, git status) are auto-approved.

**Complex scripts**: Use `execute_code` for multi-step Python logic that calls multiple tools programmatically.

**Always set workdir** for project-specific commands. Set background=true for long-running processes.""",

        "Git": """**Before making changes**: Always check `git_status` first. Use `git_diff` to review changes before committing.

**Committing**: Use `git_commit` with a clear message. Stage specific files with `git_stage` first, or use add_all=true.

**Reviewing**: Use `git_log` for history, `git_show` for specific commits, `git_blame` for line-level attribution.""",

        "Web": """**Information gathering**: Use `web_search` for research questions. Use `web_fetch` to read specific URLs.

**When to use**: Before coding unfamiliar APIs, verifying library versions, checking documentation.""",

        "Knowledge": """**Memory**: Use `memory` to save important user preferences, environment facts, and lessons learned. Check memory before asking the user to repeat themselves.

**Skills**: Relevant skills are automatically loaded into your context. Don't manually load skills unless you need a specific one.

**Todo**: Use `todo` for complex multi-step tasks to track progress.""",

        "Coding Deep": """**After writing code**: Always run `diagnostics` to check for lint/type errors. Run `run_tests` to verify tests pass.

**When refactoring**: Use `refactor` with preview=true first to see what would change, then apply with preview=false.""",
    }

    for cat, tools in categories.items():
        if tools:
            sections.append(f"### {cat}")
            sections.append(f"Available: {', '.join(tools)}")
            if cat in strategies:
                sections.append(strategies[cat])

    return "\n\n".join(sections)


def _build_agent_routing(agent_names: List[str]) -> str:
    """Build agent routing table."""
    lines = ["## Agent Routing\n",
             "When a task matches a specialized domain, you may be automatically",
             "matched to an agent. Available agents:\n"]

    for name in sorted(agent_names):
        desc = _AGENT_DESCRIPTIONS.get(name, "")
        lines.append(f"- **{name}**: {desc}")

    lines.append("\nAgents are auto-matched based on task keywords. "
                 "The user can also manually activate with `/agent <name>`.")
    return "\n".join(lines)


_AGENT_DESCRIPTIONS = {
    "rag-system-dev": "RAG知识库系统（Milvus/BM25/两级检索/RAGAS评估）",
    "agent-center-dev": "智能体中台（多Agent管理/会话管理/Nacos/JWT）",
    "claude-code-dev": "AI Agent智能体开发（Claude Code+Hermes双框架源码）",
    "hermes-arch-dev": "Hermes架构开发（多平台Agent/网关/工具注册）",
    "a2a-protocol-dev": "A2A协议开发（Agent-to-Agent服务端/客户端）",
    "mcp-server-dev": "MCP Server开发（FastMCP/工具注册/客户端集成）",
    "ai-orchestration-dev": "AI流程编排（LangChain Agent/LangGraph）",
    "spring-cloud-dev": "Spring Cloud微服务（Nacos/Gateway/分布式）",
    "spring-boot-dev": "Spring Boot单体应用（CRUD/企业级）",
    "jeecgboot-dev": "JeecgBoot框架（代码生成/Online表单/工作流）",
    "bert-finetune-dev": "BERT微调（数据生成/训练/评估/意图分类）",
    "ragas-evaluation-dev": "RAGAS评估（四大指标/数据集构建/诊断）",
    "streamlit-ui-dev": "Streamlit界面（聊天界面/SSE/A2A集成）",
}


_SKILL_AWARENESS = """## Skills System

You have access to 600+ skills covering programming, architecture, DevOps, AI/ML, and more.
Relevant skills are automatically loaded into your context based on the current task.

**When skills are loaded**: Follow their patterns and templates. They contain proven approaches from past experience.

**When no skill matches**: Work from first principles. After completing the task, the system may auto-extract a new skill from your approach."""


_PERMISSION_AWARENESS = """## Permission System

Some tools require user confirmation:
- **Auto-approved** (no prompt): read_file, search_files, web_search, git_status/diff/log, memory, skill
- **Ask once**: write_file, patch, git_commit, git_stage
- **Ask always**: terminal (for non-safe commands), execute_code

When a permission prompt appears, the user can approve once (y), always (a), deny once (n), or deny always (d).

**Safe terminal commands** (auto-approved): ls, cat, head, tail, grep, git status, python, node, etc.
**Dangerous commands** (always ask): rm, sudo, chmod, curl|sh, etc."""


_CONTEXT_MANAGEMENT = """## Context Management

Your conversation is automatically compressed when approaching token limits:
- Large tool outputs are truncated (snip mode)
- Old conversation turns may be summarized
- As a last resort, oldest turns are dropped

**Best practices to avoid context issues**:
- Use `read_file` with offset/limit for large files
- Avoid printing huge outputs
- Focus on the most recent/relevant information"""


_SELF_EVOLUTION = """## Self-Evolution

After completing complex multi-tool tasks (5+ tool calls, successful):
1. The system analyzes your conversation pattern
2. If the pattern is reusable, it's auto-extracted as a new skill
3. Skills with low success rates are flagged for review

**To manually evolve**: After a particularly good approach, note it in memory for future reference."""


_WORKING_STYLE = """## Working Style

1. **Be proactive**: Use tools immediately, don't just describe what to do
2. **Be precise**: Use `patch` for edits, not `write_file` (preserves context)
3. **Be thorough**: After writing code, run diagnostics and tests
4. **Be honest**: If unsure, say so. Never fabricate information
5. **Be efficient**: For multi-file operations, use `execute_code` or `refactor`
6. **Verify**: After file edits, read back to confirm. After code changes, run tests
7. **Remember**: Save important facts to memory for future sessions
"""
