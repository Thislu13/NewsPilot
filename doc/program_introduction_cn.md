<!--
 * @Author: WangQiushuo 185886867@qq.com
 * @Date: 2026-02-08
 * @FilePath: \code\NewsPilot\program_introduction_cn.md
 * @Description: NewsPilot 系统架构文档
 *
 * Copyright (c) 2026, All Rights Reserved.
-->

# NewsPilot 系统架构 (V0.2)

## 1. 项目概述 (Project Overview)

NewsPilot 是一套模块化的智能新闻分析系统，旨在通过自动化流水线完成全球新闻的采集、处理及语义理解。系统支持多种核心运行模式：

- **通用日报生成**: 面向行业动态的专业研报
- **投资分析**: 基于 Agent + Skill 架构的自动化价值投资分析
- **知乎热点追踪**: 社交媒体内容采集与分析
- **个性化洞察**: 基于用户画像的定制化情报

---

## 2. 目录结构 (Directory Structure)

```text
NewsPilot/
├── README.md                       # 项目说明
├── requirements.txt                # Python 依赖清单
├── config/                         # [配置中心]
│   ├── keys.py                     # API 密钥与凭证
│   ├── prompts.py                  # LLM 提示词库
│   ├── settings.py                 # 系统通用配置
│   ├── workflow_service.json       # 服务运行配置
│   ├── zhihu_user_config.py        # 知乎用户配置
│   └── docker/                     # Docker 编排文件
│
├── core/                           # [领域核心]
│   ├── news_schemas.py             # 数据模型 (Pydantic Schemas)
│   └── user_schemas.py             # 用户画像与偏好模型
│
├── data/                           # [数据存储]
│   ├── daily_reports/              # 生成的 Markdown 日报
│   │   └── YYYY-MM-DD/
│   │       ├── markdown/           # 各领域日报
│   │       └── investment/         # 投资分析报告
│   └── personal_report/            # 个性化用户洞察
│
├── doc/                            # [文档]
│   ├── program_introduction_cn.md  # 架构设计文档 (中文)
│   ├── program_introduction_en.md  # 架构设计文档 (英文)
│   └── README_en.md                # 项目说明 (英文)
│
└── src/                            # [源代码]
    │
    ├── admin/                      # [管理后台]
    │   ├── subscription_admin_server.py  # HTTP 订阅管理服务
    │   └── static/                 # 前端静态文件
    │
    ├── custom_logging/             # [日志系统]
    │   └── logging_config.py       # 统一日志配置
    │
    ├── data_acquisition/           # [数据层] (ELT 流水线)
    │   ├── daemon_orchestrator.py  # [异步] 长期驻留服务管理器
    │   ├── orchestrator.py         # [同步] 按需采集编排器
    │   ├── zhihu_daemon_orchestrator.py  # 知乎采集守护进程
    │   ├── fetchers/               # 数据源适配器
    │   │   ├── base_fetcher.py
    │   │   ├── newsapi_fetcher.py
    │   │   ├── rsshub_fetcher.py
    │   │   ├── reuters_fetcher.py
    │   │   └── zhihu_fetcher.py
    │   ├── processors/             # 处理流水线
    │   │   ├── pipeline.py
    │   │   └── module/
    │   │       ├── translator.py   # 翻译
    │   │       ├── summarizer.py   # 摘要
    │   │       ├── embedding.py    # 向量化
    │   │       └── normalize.py    # 清洗
    │   └── module/                 # 底层爬虫工具
    │       ├── download.py
    │       ├── get_content.py
    │       └── paser_html.py
    │
    ├── distribution/               # [分发层]
    │   ├── email_sender.py         # 邮件发送
    │   └── recipient_provider.py   # 订阅者管理
    │
    ├── intelligence/               # [AI 层]
    │   ├── new_analyzer.py         # 通用日报引擎
    │   ├── investment_analyzer.py  # 投资分析引擎 (Agent-based)
    │   ├── insight_generator.py    # 个性化洞察引擎
    │   ├── zhihu_analyzer.py       # 知乎内容分析引擎
    │   └── renderers/              # 报告渲染器
    │       ├── daily_report.py
    │       ├── daily_total_report.py
    │       └── zhihu_report/
    │
    ├── module/                     # [基础设施]
    │   ├── init_client.py          # LLM 客户端工厂
    │   ├── content_converter.py    # 内容转换工具
    │   ├── utils.py                # 通用工具
    │   └── agent/                  # [Agent 系统]
    │       ├── simple_agent.py     # 核心 Agent 实现
    │       ├── context.py          # 上下文管理
    │       ├── providers/          # LLM 提供商适配
    │       │   ├── base.py
    │       │   └── litellm_provider.py
    │       ├── tools/              # 工具注册与实现
    │       │   ├── registry.py
    │       │   ├── stock_data.py   # A股数据工具
    │       │   ├── stock_market.py # 市场数据工具
    │       │   ├── commodity_data.py  # 商品期货工具
    │       │   ├── filesystem.py   # 文件系统工具
    │       │   ├── shell.py        # 命令执行工具
    │       │   ├── web.py          # Web 搜索/抓取工具
    │       │   └── spawn.py        # Sub-agent 工具
    │       └── skills/             # Skill 系统
    │           ├── loader.py       # Skill 加载器
    │           ├── value-investment-strategy/  # 价值投资框架
    │           └── investment-report-skill/    # 投资日报生成
    │
    ├── storage/                    # [持久化层]
    │   ├── models.py               # SQL Alchemy ORM 模型
    │   ├── repository.py           # 数据库仓储模式
    │   ├── subscription_repository.py  # 订阅数据管理
    │   └── db_config.py            # 数据库连接设置
    │
    └── workflows/                  # [入口点]
        ├── run_service.py          # 统一服务入口
        ├── run_news_service.py     # 新闻采集服务
        ├── run_daily_report.py     # 通用日报生成
        ├── run_investment_report.py    # 投资日报生成
        ├── run_subscription_admin.py   # 订阅管理后台
        ├── main_pipeline.py        # 个性化分析流程
        └── zhihu_ananlysis_service/    # 知乎分析服务
            ├── service.py
            ├── worker.py
            └── run_zhihu_analysis_service.py
```

---

## 3. 核心架构 (Core Architecture)

本系统采用**分层架构**，将**数据生产**、**智能消费**与**分发管理**解耦。

### 3.1 基础设施层 (Infrastructure Layer)

#### A. 新闻采集服务 (News Acquisition)
负责构建高质量、持续更新的全球新闻知识库。

*   **入口点**: `src/workflows/run_news_service.py`
*   **运行模式**: 守护进程服务 (长期驻留)
*   **组件**: `DaemonOrchestrator` (`src/data_acquisition/daemon_orchestrator.py`)
*   **工作流程**:
    1.  **采集任务**: 周期性使用 `fetchers/` 中的适配器获取原始数据
    2.  **处理工作流**: 执行清洗、翻译 (LLM)、摘要 (LLM) 和向量化嵌入
    3.  **存储**: 将精炼后的数据持久化至 PostgreSQL (支持 pgvector)

#### B. 知乎采集服务 (Zhihu Acquisition)
专注于知乎平台的内容采集与分析。

*   **入口点**: `src/workflows/zhihu_ananlysis_service/run_zhihu_analysis_service.py`
*   **组件**: `ZhihuDaemonOrchestrator`, `ZhihuProcessingWorker`
*   **功能**: 采集知乎热门内容，生成结构化热点报告

### 3.2 Agent 智能层 (Agent Intelligence Layer)

> V0.2 版本引入的全新架构，基于 SimpleAgent + Skill 系统

#### SimpleAgent 架构

```
┌─────────────────────────────────────────┐
│           SimpleAgent                   │
│  ┌─────────────────────────────────┐    │
│  │  LLM Provider (LiteLLM)         │    │
│  │  - gemini/deepseek/qwen         │    │
│  └─────────────────────────────────┘    │
│  ┌─────────────────────────────────┐    │
│  │  Tool Registry                  │    │
│  │  • 股票数据 (akshare)            │    │
│  │  • 商品期货 (基差/库存/持仓)      │    │
│  │  • 文件系统 (read/list)          │    │
│  │  • Web 搜索/抓取                 │    │
│  │  • Sub-agent Spawn              │    │
│  └─────────────────────────────────┘    │
│  ┌─────────────────────────────────┐    │
│  │  Skill System                   │    │
│  │  • value-investment-strategy    │    │
│  │  • investment-report-skill      │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

#### 投资分析流程

1. **Skill 加载**: `investment-report-skill` 定义完整分析流程
2. **新闻读取**: Agent 自动读取当日各领域日报
3. **标的识别**: 识别 5-8 只潜在投资标的
4. **并行分析**: 使用 `spawn` 创建 sub-agent，并行执行深度分析
5. **价值投资框架**: 每个 sub-agent 使用 `value-investment-strategy` skill:
    - 第一层: 宏观安全过滤 (五大安全主题)
    - 第二层: 商业模式鉴定 ("求"理论)
    - 第三层: 财务分析与估值 (PE/PB/现金流/股息率)
    - 第四层: 行业差异化逻辑 (有色/银行/煤化工等)
    - 第五层: 逆向情绪风控 (人声鼎沸测试)
6. **报告生成**: 汇总分析结果，生成结构化投资日报

### 3.3 应用层 (Application Layer)

#### A. 通用情报 (日报)
*   **入口点**: `src/workflows/run_daily_report.py`
*   **引擎**: `NewsAnalyzer` (`src/intelligence/new_analyzer.py`)
*   **场景**: 定时任务 (例如：每日 8:00 AM)
*   **逻辑**: 聚合过去 24 小时的新闻，按板块分类，使用"专家展望"模型生成结构化研报

#### B. 投资情报 (投资日报)
*   **入口点**: `src/workflows/run_investment_report.py`
*   **引擎**: `InvestmentAnalyzer` (`src/intelligence/investment_analyzer.py`)
*   **依赖**: `SimpleAgent` + `investment-report-skill`
*   **场景**: 基于价值投资框架的自动化投资分析

#### C. 个性化情报 (用户洞察)
*   **入口点**: `src/workflows/main_pipeline.py`
*   **引擎**: `InsightGenerator` (`src/intelligence/insight_generator.py`)
*   **场景**: 按需触发或用户触发
*   **逻辑**: 加载用户画像（持仓、兴趣、风险偏好），生成独家洞察

### 3.4 分发管理层 (Distribution Layer)

#### 订阅管理系统
*   **入口**: `src/workflows/run_subscription_admin.py`
*   **功能**: HTTP Web 后台管理订阅者
*   **数据表**: `subscription_targets` 存储订阅者信息

#### 邮件分发
*   **组件**: `EmailSender` (`src/distribution/email_sender.py`)
*   **功能**: 支持 SMTP 邮件分发，动态读取订阅列表

---

## 4. 关键技术组件 (Key Technical Components)

### 4.1 数据层 (`src/data_acquisition`)
*   **Fetchers**: 模块化适配器支持多种新闻源
*   **Processors**: 流水线架构 (`pipeline.py`)，编排翻译、摘要、向量化等步骤

### 4.2 Agent 层 (`src/module/agent`)
*   **SimpleAgent**: 核心 Agent 实现，支持工具调用和 sub-agent 创建
*   **LiteLLM Provider**: 统一接口支持 Gemini/DeepSeek/Qwen 等多个模型
*   **Tool Registry**: 动态工具注册与管理
*   **Skill Loader**: Markdown-based Skill 加载系统

### 4.3 工具集 (`src/module/agent/tools`)
| 工具 | 功能 | 数据源 |
|-----|------|--------|
| `A_Stock_Profile` | A股个股基本面 | akshare |
| `A_Stock_Price_History` | 历史价格数据 | akshare |
| `A_Stock_Technical_Indicators` | 技术指标 | akshare |
| `Commodity_Futures_Basis_Overview` | 商品期货基差 | akshare |
| `Commodity_Inventory_Or_Receipt` | 库存/仓单数据 | akshare |
| `WebSearch/WebFetch` | Web 搜索与抓取 | Brave API |
| `Spawn` | 创建 Sub-agent | - |

### 4.4 存储层 (`src/storage`)
*   **Repository Pattern**: 抽象数据库交互
*   **SubscriptionRepository**: 订阅管理专用仓储
*   **pgvector**: 支持向量存储与语义检索

---

## 5. 运行模式详解 (Operation Modes)

### 5.1 服务化运行 (推荐用于生产)

```bash
# 统一入口，通过 workflow_service.json 配置
python -m src.workflows.run_service

# 单独启动新闻采集服务
python -m src.workflows.run_news_service

# 单独启动知乎采集服务
python -m src.workflows.zhihu_ananlysis_service.run_zhihu_analysis_service

# 启动订阅管理后台
python -m src.workflows.run_subscription_admin
```

### 5.2 任务化运行 (推荐用于定时任务)

```bash
# 生成通用日报
python -m src.workflows.run_daily_report

# 生成投资日报
python -m src.workflows.run_investment_report --date 2026-03-15

# 生成个性化洞察
python -m src.workflows.main_pipeline
```

---

## 6. 发布状态 (V0.2)

### V0.2 新增功能
*   **Agent 投资分析系统**: 基于 SimpleAgent + Skill 的自动化价值投资分析
*   **知乎热点追踪**: 新增知乎内容采集与分析服务
*   **订阅管理系统**: Web 后台管理订阅者与分发配置
*   **Skill 系统**: Markdown-based 可扩展 Skill 框架
*   **多模型支持**: 通过 LiteLLM 统一接入 Gemini/DeepSeek/Qwen

### 功能能力
*   从采集到分析的全栈自动化
*   双模式运行（后台服务 + 按需报告）
*   Agent 驱动的智能投资分析
*   灵活的订阅管理与分发

### 基础设施
*   PostgreSQL + pgvector
*   Docker 容器化支持
*   统一日志系统

---

*本文档最后更新：2026-03-15*
