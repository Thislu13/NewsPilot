<div align="center">

# 📰 NewsPilot
### 智能新闻情报分析系统 (Intelligent News Intelligence Analysis System)

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Supported-blue?logo=docker)]()
[![Model](https://img.shields.io/badge/Powered%20By-LLM-green)]()

**NewsPilot** 是一套基于大语言模型（LLM）的自动化情报分析系统，旨在将海量全球新闻转化为**结构化事件图谱、个性化洞察与可执行的建议**。它不仅仅是一个新闻整合工具，更是一个能够理解你职业、持仓和兴趣的 7×24h 智能情报助理。

🔗 **在线体验**: [www.newspilot.cc](https://www.newspilot.cc) — 实时展示 AI 自动构建的全球新闻事件图谱

[English Doc/English README](doc/README_en.md) |
[📖 架构设计文档 (中文版)](doc/program_introduction_cn.md) |
[📊 领域日报演示](data/daily_reports/2026-01-30) |
[🎯 个人洞察演示](data/personal_report/2026-01-11/daily_report.md)

> 💡 **看着不错！但不想部署，需要每日自动推送？**
> 如果您有每日自动接收定制化日报的需求（如通过邮件、飞书、钉钉推送），请通过邮件`1835886867@qq.com` 联系作者。

</div>

---

## ✨ 核心能力

| 模块 | 功能描述 | 关键技术 |
| :--- | :--- | :--- |
| **🌍 全球采集** | 集成 NewsAPI、RSSHub、Reuters、知乎等多源数据，自动清洗去重。 | `Playwright`, `Feedparser` |
| **🧠 深度理解** | 内置多模型翻译引擎，自动将外媒新闻转化为中文精要；基于语义的向量化编码。 | `DeepSeek`, `Qwen-Embedding` |
| **🕸️ 事件图谱** | 从新闻中抽取独立事件，通过 UMAP + HDBSCAN + LLM 智能聚类，构建多层树形事件簇，自动追踪热点演变。 | `UMAP`, `HDBSCAN` |
| **🎯 双轨情报** | **Track A (通用)**: 每日自动聚合十大板块，生成行业深度研报。<br>**Track B (个性)**: 基于用户画像 (持仓/职业)，检索相关新闻生成专属建议。 | `Gemini-Thinking` |
| **🤖 Agent 投资分析** | 基于 SimpleAgent + Skill 架构，使用"五层价值投资框架"自动生成投资日报。 | `LiteLLM`, `akshare` |
| **📊 知乎热点追踪** | 自动采集知乎热门内容，生成结构化热点分析报告。 | `ZhihuFetcher` |
| **📧 订阅分发** | 支持邮件分发，内置订阅管理后台，动态配置接收者和报告类型。 | `SMTP`, `HTTP Server` |
| **☁️ 远程同步** | 本地事件图谱自动同步到远程服务器，驱动 www.newspilot.cc 前端实时展示。 | `pg_dump`, `SCP` |

---

## 🏗️ 快速开始

### 1. 环境准备

- **Python 3.12+**
- **Docker** (推荐，用于快速部署 PostgreSQL 和 RSSHub)
- **API Keys**:
  - `Google Gemini` / `OpenAI` / `DeepSeek` / `Qwen`: 用于核心推理、翻译与摘要。
  - `NewsAPI` (或其他 RSS 源): 用于数据采集。

### 2. 安装与配置

```bash
# 1. 克隆仓库
git clone https://github.com/Thislu13/NewsPilot.git
cd NewsPilot

# 2. 安装依赖
pip install -r requirements.txt
```

**配置 API 密钥**:
编辑 `config/keys.py`:
```python
openai_api = "your keys"
deepseek_api = "your keys"
gemini_api = "your keys"
qwen_api = "your keys"
```

**启动基础设施 (Docker)**:
```bash
# Windows
docker-compose -f config/docker/docker-compose_postgresql_win.yml up -d
docker-compose -f config/docker/docker-compose_rsshub_win.yml up -d

# Linux/Mac
# 使用 config/docker/docker-compose_postgresql_ubuntu22.04.yml 等对应文件
```

### 3. 运行模式

| 模式 | 命令 | 说明 |
| :--- | :--- | :--- |
| **统一入口** | `python -m src.workflows.run_service` | 读取 `config/workflow_service.json`，按配置启动 `news` 或 `zhihu_analysis` 服务。 |
| **新闻采集服务** | `python -m src.workflows.run_news_service` | **[推荐]** 生产模式。后台驻留，每120分钟轮询采集、清洗入库。 |
| **知乎采集服务** | `python -m src.workflows.zhihu_ananlysis_service.run_zhihu_analysis_service` | 知乎内容采集与分析服务。 |
| **事件图谱服务** | `python -m src.workflows.run_graph_service` | 启动建图守护进程，定点执行事件聚类、描述更新与远程同步。 |
| **通用日报** | `python -m src.workflows.run_daily_report` | 手动/定时触发。分析当日新闻，生成通用行业日报。 |
| **投资日报** | `python -m src.workflows.run_investment_report --date 2026-03-15` | 基于价值投资框架生成投资分析报告。 |
| **个性化洞察** | `python -m src.workflows.main_pipeline` | 读取 `user_profile.json`，生成针对个人的投资与行动建议。 |
| **订阅管理** | `python -m src.workflows.run_subscription_admin` | 启动订阅管理 Web 后台 (默认端口 18000)。 |

---

## 🧩 系统架构

### 分层架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    [应用层] 情报输出                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ 通用日报引擎  │ │ 投资分析引擎  │ │ 个性化洞察引擎        │ │
│  │ NewsAnalyzer │ │ Investment   │ │ InsightGenerator     │ │
│  └──────────────┘ │   Analyzer   │ └──────────────────────┘ │
│                   └──────────────┘                           │
├─────────────────────────────────────────────────────────────┤
│                    [Agent 层] 智能代理                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              SimpleAgent + Skill 系统                  │  │
│  │  • 工具调用 (股票数据、商品期货、文件系统、Web搜索)      │  │
│  │  • Sub-agent 并行分析                                   │  │
│  │  • 价值投资五层框架 (value-investment-strategy)        │  │
│  └───────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    [图谱层] 事件理解与聚类                     │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Event Graph (事件图谱)                    │  │
│  │  • 事件抽取 (EventExtractor)                           │  │
│  │  • 智能聚类 (UMAP + HDBSCAN + LLM)                     │  │
│  │  • 树形簇结构 (EventCluster)                           │  │
│  │  • 每日/每周描述自动更新                                │  │
│  └───────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    [数据层] 采集与处理                        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │   Fetchers   │ │  Processors  │ │      Storage         │ │
│  │  (多源采集)   │ │ (清洗/翻译/  │ │   (PostgreSQL +      │ │
│  │              │ │  摘要/事件)   │ │    pgvector)         │ │
│  └──────────────┘ └──────────────┘ └──────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    [基础设施] 管理与分发                      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ 订阅管理后台  │ │   邮件分发    │ │   知乎/图谱服务       │ │
│  └──────────────┘ └──────────────┘ └──────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 核心工作流

#### Step 1: 基础设施 (Infrastructure)
> 后台默默运行，构建专属知识库

1. **采集**: `DaemonOrchestrator` / `ZhihuDaemonOrchestrator` 定时调度 Fetchers
2. **加工**: `ProcessorPipeline` 流水线处理：
    - 🧹 **清洗**: 去除广告、标准化格式
    - 🔄 **翻译**: 调用 DeepSeek/GPT 将外文互译
    - 📝 **摘要**: 提取核心事实，去除冗余
    - 🕸️ **事件抽取**: 使用 LLM 从新闻中提取独立事件并生成 embedding

#### Step 2: 事件图谱 (Event Graph)
> 理解新闻背后的真实世界

- **建图守护进程**: `GraphDaemon` 定点调度（UTC 0/6/12/18 点）
- **事件入库**: 事件匹配 → 智能聚类 (`UMAP` + `HDBSCAN`) → LLM 审核归属 → 簇分裂/合并
- **描述更新**: 每日自动更新 `recent_description`，每周日执行全量 `weekly_description` + `detailed_description` 更新
- **远程同步**: 自动推送至远程服务器，驱动前端展示

#### Step 3: 智能分析 (Intelligence)
> 当你需要情报时，大脑开始工作

- **通用日报**: `NewsAnalyzer` 提取最近 24h 新闻 → 按板块聚类 → 专家模型分析 → 输出 Markdown 日报
- **投资分析**: `InvestmentAnalyzer` → `SimpleAgent` + `investment-report-skill` → 五层价值投资框架 → 输出投资日报
- **个性洞察**: `InsightGenerator` 读取用户画像 → 检索强相关新闻 → 生成"机会/风险"评估

#### Step 4: 分发与展示 (Distribution)
> 让情报触达用户

- **订阅管理**: Web 后台管理订阅者、报告类型、生效时间
- **邮件推送**: 支持 SMTP 邮件分发，动态读取订阅列表
- **在线展示**: [www.newspilot.cc](https://www.newspilot.cc) 实时展示事件图谱的新信号与热点追踪

---

## 🕸️ 事件图谱系统

NewsPilot 引入了全新的 **Event Graph** 架构，将海量新闻转化为结构化、可追踪的事件网络：

### 核心特性

- **事件级抽取**: 从单条新闻中提取多条独立事件，而非整篇向量化
- **智能聚类**: `UMAP`(768D→30D) + `HDBSCAN` 自动发现事件簇，LLM 审核归属
- **树形层级**: 支持多层簇结构 (`depth`)，大簇自动分裂为子话题
- **动态描述**: 每日自动更新簇的近期描述，每周生成周度综述与详细分析
- **远程同步**: 本地 PostgreSQL 自动同步至远程，驱动 Web 前端实时展示

### 数据库表结构

| 表名 | 说明 |
|------|------|
| `candidate_events` | 待处理事件队列 |
| `processed_events` | 已归簇事件（含 embedding） |
| `event_clusters` | 事件簇（树形结构，含 centroid、描述字段） |
| `event_membership` | 事件-簇多对多关系 |

### 使用示例

```bash
# 启动事件图谱守护进程（定点建图 + 周日定期更新）
python -m src.workflows.run_graph_service
```

---

## 🤖 Agent 投资分析系统

NewsPilot 引入了全新的 **SimpleAgent** 架构，用于自动化投资分析：

### 核心特性

- **Skill 驱动**: 通过 `investment-report-skill` 定义完整分析流程
- **五层价值投资框架**: 宏观安全 → 商业模式 → 财务估值 → 行业逻辑 → 逆向风控
- **工具丰富**: 集成 A股数据、商品期货、技术指标等工具
- **并行分析**: 使用 `spawn` 创建 sub-agent 并行分析多只股票

### 使用示例

```bash
# 生成今日投资日报
python -m src.workflows.run_investment_report

# 指定日期和模型
python -m src.workflows.run_investment_report --date 2026-03-15 --model gemini --max-stocks 8
```

---

## 📋 订阅管理系统

内置 HTTP 订阅管理后台，支持：

- 添加/删除订阅者
- 配置报告类型（通用日报、知乎报告、投资日报等）
- 设置生效时间段
- 启用/禁用订阅

```bash
# 启动订阅管理后台
python -m src.workflows.run_subscription_admin

# 访问 http://localhost:18000
```

---

## 🙏 致谢 (Acknowledgments)

本项目之所以能够实现，离不开以下卓越的基础模型与开源服务的支持：

*   **核心推理**: [Google Gemini](https://ai.google.dev/) (Thinking Model), [OpenAI GPT](https://openai.com/), [DeepSeek](https://www.deepseek.com/)
*   **语义向量**: [Qwen (通义千问)](https://tongyi.aliyun.com/) - 提供优秀的中文语义向量支持
*   **数据源**: [NewsAPI](https://newsapi.org/), [Reuters](https://www.reuters.com/), 知乎
*   **股票数据**: [akshare](https://www.akshare.xyz/) - 中国财经数据接口库

---

## ⚠️ 版权与许可 (License)

本项目采用 **MIT 许可证 (MIT License)**。

您可以自由地使用、修改和分发本项目的源代码，包括用于商业用途。只需在软件副本中包含原作者的版权声明和许可声明即可。

**免责声明**: 本系统生成的投资建议与分析仅供参考，不构成实际投资依据。投资有风险，入市需谨慎。

---

## 🤝 参与贡献 (Contribute)

NewsPilot 仍在快速迭代中，非常欢迎您的加入！

*   **Star 🌟**: 如果觉得项目不错，请点击右上角 Star 支持一下！
*   **Fork & PR**: 欢迎提交代码修复 Bug 或增加新特性 (如对接更多新闻源、Web UI 优化等)。
*   **Issue**: 遇到问题或有新想法？请提交 Issue 讨论。

---

## 📬 联系作者 (Contact)

*   **Author**: Wang Qiushuo
*   **Email**: 1835886867@qq.com
*   **GitHub**: [NewsPilot Repository](https://github.com/Thislu13/NewsPilot)

---

<div align="center">
  <sub>Generated by NewsPilot Team · 2026</sub>
</div>
