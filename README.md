# 🐺 Wolf Agent

Universal AI Agent with top-tier coding capabilities.

Wolf融合了 Hermes Agent 的全能工具体系和 Claude Code 的顶级编程能力，是一个可以直接在终端使用的通用AI智能体。

## Features

- **原生编程能力** — 终端执行、文件读写编辑、代码搜索、精确补丁
- **多Provider支持** — Anthropic/OpenAI/MiMo/DeepSeek/Ollama
- **技能系统** — 兼容 Hermes SKILL.md 和 Claude Code skills 格式
- **记忆系统** — 跨会话持久化记忆
- **自进化** — 从成功模式中自动提取技能
- **Fallback链** — 多Provider自动故障转移

## Install

```bash
cd wolf && pip install -e .
```

## Usage

```bash
wolf                 # Interactive REPL
wolf -p "message"    # Single message mode
wolf --model xxx     # Override model
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Branch Strategy

- `main` — Stable releases (tagged)
- `develop` — Development integration
- `feature/phase-N-*` — Feature branches
- `bugfix/*` — Bug fixes
