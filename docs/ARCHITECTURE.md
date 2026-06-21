# Wolf Agent — 架构设计文档

## 定位

Wolf 是一个融合 Hermes Agent 全能工具体系 + Claude Code 顶级编程能力的通用 AI 智能体。
核心理念：**一个终端，全能助手，直接编程，持续进化**。

## 与 Hermes / Claude Code 的关系

| 维度 | Hermes | Claude Code | Wolf |
|------|--------|-------------|------|
| 语言 | Python | TypeScript | Python |
| 定位 | 多平台通用 Agent | 编程专用 Agent | 通用+编程一体 |
| 工具系统 | registry 自注册 | Tool 接口+buildTool | registry 自注册（增强） |
| 编程能力 | 通过 delegate_task 调用 CC | 原生强大 | 内置原生编程工具链 |
| 技能系统 | SKILL.md + 目录 | SKILL.md + 目录 | 兼容两者格式 |
| Agent | 无永久 Agent | ~/.claude/agents | ~/.wolf/agents（兼容 CC 格式） |
| 记忆 | MEMORY.md + memory tool | 自动记忆 | 结构化记忆系统 |
| 自进化 | skill_manage 手动 | 无 | 自动 skill 提取 |
| Provider | 20+ provider | Anthropic only | 多 provider fallback |

## 核心架构

```
wolf/
├── wolf/                      # Python 主包
│   ├── __init__.py
│   ├── cli.py                 # CLI 入口 + REPL 循环
│   ├── agent.py               # WolfAgent 主类
│   ├── conversation_loop.py   # 对话循环核心引擎
│   ├── tools/                 # 工具系统
│   │   ├── registry.py        # 工具注册表（单例）
│   │   ├── terminal_tool.py   # Shell 执行
│   │   ├── file_tools.py      # 文件读写编辑搜索
│   │   ├── patch_tool.py      # 精确补丁
│   │   ├── web_tools.py       # Web 搜索/抓取
│   │   ├── memory_tool.py     # 记忆管理
│   │   ├── skill_tool.py      # 技能加载/管理
│   │   ├── agent_tool.py      # Agent 编排
│   │   ├── todo_tool.py       # 任务管理
│   │   ├── cron_tool.py       # 定时任务
│   │   ├── image_tool.py      # 图像分析
│   │   ├── tts_tool.py        # 语音合成
│   │   └── execute_code_tool.py # 批量代码执行
│   ├── providers/             # LLM Provider 适配
│   │   ├── base.py            # Provider 抽象基类
│   │   ├── anthropic.py       # Anthropic/Claude
│   │   ├── openai.py          # OpenAI 兼容
│   │   ├── xiaomi.py          # 小米 MiMo
│   │   ├── deepseek.py        # DeepSeek
│   │   └── ollama.py          # Ollama 本地
│   ├── skills/                # 技能系统
│   │   ├── loader.py          # 技能加载器
│   │   ├── trigger.py         # 技能触发匹配
│   │   └── evolve.py          # 自动进化引擎
│   ├── agents/                # Agent 系统
│   │   ├── loader.py          # Agent 定义加载
│   │   └── executor.py        # Agent 执行器
│   ├── memory/                # 记忆系统
│   │   ├── store.py           # 持久化存储
│   │   └── context.py         # 上下文注入
│   ├── config/                # 配置系统
│   │   ├── settings.py        # 配置加载/管理
│   │   └── models.py          # 模型路由
│   └── ui/                    # 终端 UI
│       ├── repl.py            # REPL 交互
│       ├── renderer.py        # 输出渲染
│       └── theme.py           # 主题配色
├── setup.py                   # 安装配置
├── pyproject.toml
├── config.example.yaml        # 配置示例
└── tests/                     # 测试
```

## 分支策略

- `main` — 稳定发布版本，tag 标记
- `develop` — 开发集成分支
- `feature/phase-N-*` — 功能开发分支
- `bugfix/*` — Bug 修复分支

合并路径：feature → develop → main（tag 发布）

## 开发阶段

### Phase 1: 核心骨架（feature/phase1-core）
- 项目结构 + 配置系统
- 工具注册表 + 核心工具（terminal, file, search, patch）
- 对话循环引擎
- CLI 入口 + REPL
- Anthropic Provider

### Phase 2: 编程增强（feature/phase2-coding）
- 精确文件编辑（fuzzy match patch）
- 批量代码执行（execute_code）
- Git 集成工具
- LSP 诊断集成
- 文件变更追踪

### Phase 3: 技能与记忆（feature/phase3-skills-memory）
- 技能加载系统（兼容 Hermes SKILL.md + Claude Code skills）
- 记忆系统（结构化持久化）
- Agent 加载系统（兼容 ~/.claude/agents）
- 上下文构建引擎

### Phase 4: 多 Provider（feature/phase4-providers）
- OpenAI 兼容 Provider
- MiMo / DeepSeek Provider
- Ollama Provider
- Fallback Chain

### Phase 5: 自进化与 UI（feature/phase5-evolution-ui）
- 自动技能提取（从成功模式中学习）
- 终端 UI 美化（Rich + 主题）
- 配置向导
- 安装脚本 + `wolf` 命令

## 关键设计模式

### 1. 工具注册（来自 Hermes）
```python
# 模块级自注册
registry.register(
    name="terminal",
    toolset="terminal",
    schema={...},
    handler=terminal_handler,
    check_fn=check_terminal_available,
)
```

### 2. 对话循环（融合两者）
```
用户输入 → 构建 system prompt（记忆+技能+上下文）
  → LLM API 调用（流式，重试，fallback）
  → 工具调用（并发判断，顺序/并行执行）
  → 继续循环 / 返回最终响应
  → 后处理（记忆同步，技能审查，会话持久化）
```

### 3. 编程工具链（来自 Claude Code）
- terminal: Shell 执行，支持 background process
- file_read: 带行号和分页的文件读取
- file_write: 全量文件写入
- file_edit: 精确 find-and-replace（模糊匹配）
- search_files: ripgrep 加速的内容/文件搜索
- execute_code: Python 脚本批量执行工具调用

### 4. 自进化机制（Wolf 独创）
```
任务完成 → 分析对话模式
  → 如果发现可复用模式 → 自动提取为 skill
  → skill 触发条件、步骤、验证方式
  → 下次类似任务自动加载
```
