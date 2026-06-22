# 🐺 Wolf Agent

Universal AI Agent with top-tier coding capabilities.

Wolf 融合了 Hermes Agent 的全能工具体系和 Claude Code 的顶级编程能力，是一个可以直接在终端使用的通用 AI 智能体。它能持续学习和进化自己的能力。

## 快速开始

```bash
# 安装
cd wolf && pip install -e .

# 首次配置（交互式向导）
wolf setup

# 启动
wolf                 # 交互式 REPL
wolf -p "任务描述"    # 单次执行模式
```

## 核心能力

### 🔧 26 个内置工具
| 类别 | 工具 |
|------|------|
| 文件 | read_file, write_file, patch, search_files, notebook_read/edit/create |
| 执行 | terminal, execute_code |
| Git | git_status, git_diff, git_log, git_show, git_blame, git_commit, git_branch, git_stage, git_file_history |
| 编程 | diagnostics (ruff/mypy/eslint), run_tests (pytest/jest/go), refactor |
| Web | web_search, web_fetch |
| 知识 | memory, skill, todo |

### 🤖 13 个专业 Agent
自动匹配任务到专业领域：RAG系统、智能体中台、Spring Cloud、JeecgBoot、BERT微调、MCP Server、A2A协议、LangGraph编排等。

### 📚 646 个技能
融合 Wolf + Claude Code + Hermes 三方技能库，智能触发，自动注入 system prompt。

### 🗜️ 上下文压缩
3 层策略（snip/summarize/drop），自动在 75% token 阈值触发，支持紧急 overflow 恢复。

### 🔒 权限系统
4 级权限（auto_allow/ask_once/ask_always/deny），Shell 命令安全分类，交互式 y/n/a/d 确认。

### 🔄 自进化
自动从成功模式中提取技能，追踪技能质量评分，从失败中学习改进。

## REPL 命令

```
/help              显示帮助
/tools             列出所有工具
/agents            列出所有 Agent
/agent <name>      激活 Agent
/skills            列出所有技能
/permissions       查看权限规则
/perm <tool> <lvl> 设置权限
/sessions          查看历史会话
/resume <id>       恢复会话
/memory            查看记忆
/model             查看/切换模型
/version           版本信息
```

## 多 Provider 支持

| Provider | 模型 |
|----------|------|
| 小米 MiMo | mimo-v2.5-pro (默认) |
| DeepSeek | deepseek-chat |
| Anthropic | claude-sonnet-4 |
| OpenAI | gpt-4o |
| Ollama | 本地模型 |

支持 Fallback Chain — 主 Provider 失败自动切换。

## 项目结构

```
wolf/
├── wolf/
│   ├── agent.py              # 主 Agent 类
│   ├── conversation_loop.py   # 对话循环引擎
│   ├── cli.py                 # CLI 入口 + REPL
│   ├── tools/                 # 26 个工具
│   ├── providers/             # 5 个 Provider
│   ├── skills/                # 技能系统 + 触发器 + 进化
│   ├── agents/                # Agent 加载 + 执行
│   ├── permissions/           # 权限系统
│   ├── context/               # 上下文压缩
│   ├── hooks/                 # Hook 系统
│   ├── mcp/                   # MCP 客户端
│   ├── sessions/              # 会话持久化
│   ├── memory/                # 记忆存储
│   ├── config/                # 配置 + Prompt Builder
│   └── ui/                    # 终端 UI (Rich渲染 + 权限提示)
├── docs/ARCHITECTURE.md
├── pyproject.toml
└── config.example.yaml
```

## 版本历史

v0.1.0 ~ v1.1.0 — 12 个版本，详见 Git tags

## 许可

MIT
