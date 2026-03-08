# Simple Agent

一个完整的、独立的智能体框架实现,专为单次调用场景设计。

## 特性

✅ **完整功能**
- LLM 交互与工具调用
- Skills 加载系统
- 文件系统工具 (读/写/编辑/列表)
- Shell 执行工具
- Web 工具 (搜索/抓取)
- Sub-Agent 支持

✅ **独立实现**
- 不依赖任何外部 Agent 框架
- 参考 nanobot 架构但完全独立编写
- 约 1650 行代码

✅ **简洁设计**
- 无状态,每次调用独立
- 无记忆管理
- 无多渠道通信
- 专注单次问答场景

## 快速开始

### 安装依赖

```bash
pip install litellm aiohttp loguru
```

### 基本使用

```python
import asyncio
from pathlib import Path
from src.module.agent import SimpleAgent, LiteLLMProvider

async def main():
    # 初始化 Provider
    provider = LiteLLMProvider(
        api_key="your-api-key",
        default_model="gemini/gemini-2.0-flash-exp",
    )

    # 创建 Agent
    async with SimpleAgent(
        provider=provider,
        workspace=Path("./workspace"),
        max_iterations=40,
    ) as agent:
        # 单次调用
        response = await agent.ask("列出当前目录的文件")
        print(response)

asyncio.run(main())
```

### 使用 Gemini

```python
provider = LiteLLMProvider(
    api_key="AIzaSy...",
    default_model="gemini/gemini-2.0-flash-exp",
)

agent = SimpleAgent(provider=provider, workspace=Path("."))
response = await agent.ask("你的问题")
```

### 启用 Web 搜索

```python
agent = SimpleAgent(
    provider=provider,
    workspace=Path("."),
    brave_api_key="your-brave-api-key",  # 启用 web_search 工具
)
```

### 使用 Sub-Agent

Agent 可以自动使用 `spawn` 工具创建子智能体处理复杂子任务:

```python
response = await agent.ask(
    "分析这个项目的架构,并为每个模块生成文档"
)
# Agent 可能会 spawn 多个 sub-agent 分别处理不同模块
```

## 架构

```
src/module/agent/
├── simple_agent.py          # 主 Agent 类
├── providers/               # LLM 提供商
│   ├── base.py
│   └── litellm_provider.py
├── tools/                   # 工具系统
│   ├── base.py
│   ├── registry.py
│   ├── filesystem.py
│   ├── shell.py
│   ├── web.py
│   └── spawn.py
├── skills/                  # Skills 系统
│   └── loader.py
└── context.py               # 上下文构建器
```

## 可用工具

- `read_file` - 读取文件
- `write_file` - 写入文件
- `edit_file` - 编辑文件 (查找替换)
- `list_dir` - 列出目录
- `exec` - 执行 Shell 命令
- `web_search` - Web 搜索 (需要 Brave API key)
- `web_fetch` - 抓取网页
- `spawn` - 创建 Sub-Agent

## Skills 系统

在 `workspace/skills/` 目录下创建技能:

```
workspace/skills/
└── my-skill/
    └── SKILL.md
```

SKILL.md 示例:

```markdown
---
description: "My custom skill"
always: "true"
---

# My Skill

This skill teaches the agent how to...
```

## 配置选项

```python
SimpleAgent(
    provider=provider,           # LLM 提供商 (必需)
    workspace=Path("."),         # 工作空间 (必需)
    model="gemini/...",          # 模型名称
    max_iterations=40,           # 最大迭代次数
    temperature=0.1,             # 温度
    max_tokens=4096,             # 最大 tokens
    brave_api_key=None,          # Brave 搜索 API key
    exec_timeout=120,            # Shell 超时(秒)
    restrict_to_workspace=False, # 限制文件操作在工作空间内
    enable_spawn=True,           # 启用 sub-agent
)
```

## 与 nanobot 的对比

| 特性 | nanobot AgentLoop | SimpleAgent |
|------|-------------------|-------------|
| LLM 调用 | ✅ | ✅ |
| 工具执行 | ✅ | ✅ |
| Skills 加载 | ✅ | ✅ |
| Sub-Agent | ✅ | ✅ |
| 多轮迭代 | ✅ | ✅ |
| 记忆管理 | ✅ | ❌ |
| 会话持久化 | ✅ | ❌ |
| MessageBus | ✅ | ❌ |
| 多渠道支持 | ✅ | ❌ |
| 依赖 nanobot | ✅ | ❌ |

## 许可证

MIT
