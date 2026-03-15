<div align="center">

# 📰 NewsPilot
### Intelligent News Intelligence Analysis System

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Supported-blue?logo=docker)]()
[![Model](https://img.shields.io/badge/Powered%20By-LLM-green)]()

> ⚠️ **Note**: This documentation is translated from the Chinese version. In case of any discrepancy, the [Simplified Chinese version](../README.md) shall prevail.

**NewsPilot** is an automated intelligence analysis system based on Large Language Models (LLM), designed to transform massive global news into **personalized, actionable insights**. It is not just a news aggregation tool, but a 24/7 intelligent intelligence assistant that understands your profession, holdings, and interests.

[Simplified Chinese/简体中文](../README.md) |
[📖 Architecture Documentation (English)](program_introduction_en.md) |
[📊 Industry Daily Report Demo](../data/daily_reports/2026-01-30) |
[🎯 Personal Insight Demo](../data/personal_report/2026-01-11/daily_report.md)

> 💡 **Looks good! But don't want to deploy, need daily auto-push?**
> If you have a need for daily customized daily reports delivered automatically (e.g., via Email, Feishu, DingTalk), please contact the author via email: `1835886867@qq.com`.

</div>

---

## ✨ Core Capabilities

| Module | Description | Key Tech |
| :--- | :--- | :--- |
| **🌍 Global Acquisition** | Integrates multi-source data from NewsAPI, RSSHub, Reuters, Zhihu, with automatic cleaning and deduplication. | `Playwright`, `Feedparser` |
| **🧠 Deep Understanding** | Built-in multi-model translation engine, automatically converting foreign news into concise summaries; semantic-based vector encoding. | `DeepSeek`, `Qwen-Embedding` |
| **🎯 Dual-Track Intel** | **Track A (General)**: Automatically aggregates top 10 sectors daily, generating in-depth industry reports.<br>**Track B (Personalized)**: Based on user profiles (Holdings/Profession), retrieves relevant news to generate exclusive suggestions. | `Gemini-Thinking` |
| **🤖 Agent Investment Analysis** | Based on SimpleAgent + Skill architecture, using "Five-Layer Value Investment Framework" to automatically generate investment daily reports. | `LiteLLM`, `akshare` |
| **📊 Zhihu Hot Topics** | Automatically acquires Zhihu trending content and generates structured hotspot analysis reports. | `ZhihuFetcher` |
| **📧 Subscription Distribution** | Supports email distribution with built-in subscription management backend for dynamic configuration of recipients and report types. | `SMTP`, `HTTP Server` |

---

## 🏗️ Quick Start

### 1. Prerequisites

- **Python 3.12+**
- **Docker** (Recommended, for quick deployment of PostgreSQL and RSSHub)
- **API Keys**:
  - `Google Gemini` / `OpenAI` / `DeepSeek` / `Qwen`: For core reasoning, translation, and summarization.
  - `NewsAPI` (or other RSS sources): For data acquisition.

### 2. Installation & Configuration

```bash
# 1. Clone repository
git clone https://github.com/Thislu13/NewsPilot.git
cd NewsPilot

# 2. Install dependencies
pip install -r requirements.txt
```

**Configure API Keys**:
Edit `config/keys.py`:
```python
openai_api = "your keys"
deepseek_api = "your keys"
gemini_api = "your keys"
qwen_api = "your keys"
```

**Start Infrastructure (Docker)**:
```bash
# Windows
docker-compose -f config/docker/docker-compose_postgresql_win.yml up -d
docker-compose -f config/docker/docker-compose_rsshub_win.yml up -d

# Linux/Mac
# Use config/docker/docker-compose_postgresql_ubuntu22.04.yml etc.
```

### 3. Running Modes

| Mode | Command | Description |
| :--- | :--- | :--- |
| **Unified Entry** | `python -m src.workflows.run_service` | Reads `config/workflow_service.json`, starts `news` or `zhihu_analysis` service. |
| **News Service** | `python -m src.workflows.run_news_service` | **[Recommended]** Production mode. Runs in background, polls collection every 120 mins, cleans and stores data. |
| **Zhihu Service** | `python -m src.workflows.zhihu_ananlysis_service.run_zhihu_analysis_service` | Zhihu content acquisition and analysis service. |
| **General Report** | `python -m src.workflows.run_daily_report` | Manual/Scheduled trigger. Analyzes daily news, generates general industry daily reports. |
| **Investment Report** | `python -m src.workflows.run_investment_report --date 2026-03-15` | Generates investment analysis reports based on value investment framework. |
| **Personal Insight** | `python -m src.workflows.main_pipeline` | Reads `user_profile.json`, generates personalized investment and action suggestions. |
| **Subscription Admin** | `python -m src.workflows.run_subscription_admin` | Starts subscription management Web backend (default port 18000). |

---

## 🧩 System Architecture

### Layered Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    [Application Layer]                      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ General      │ │ Investment   │ │ Personalized         │ │
│  │ NewsAnalyzer │ │ Analyzer     │ │ InsightGenerator     │ │
│  └──────────────┘ └──────────────┘ └──────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    [Agent Layer]                            │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              SimpleAgent + Skill System                │  │
│  │  • Tool Calling (Stock Data, Commodity, Web Search)   │  │
│  │  • Sub-agent Parallel Analysis                        │  │
│  │  • Value Investment Five-Layer Framework              │  │
│  └───────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    [Data Layer]                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │   Fetchers   │ │  Processors  │ │      Storage         │ │
│  │  (Multi-src) │ │ (Clean/Trans │ │   (PostgreSQL +      │ │
│  │              │ │ /Sum/Embed)  │ │    pgvector)         │ │
│  └──────────────┘ └──────────────┘ └──────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    [Infrastructure]                         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ Subscription │ │   Email      │ │   Zhihu Service      │ │
│  │ Admin Backend│ │ Distribution │ │                      │ │
│  └──────────────┘ └──────────────┘ └──────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Core Workflow

#### Step 1: Infrastructure
> Runs silently in the background, building an exclusive knowledge base

1. **Collection**: `DaemonOrchestrator` / `ZhihuDaemonOrchestrator` schedules Fetchers periodically
2. **Processing**: `ProcessorPipeline` pipeline processing:
    - 🧹 **Cleaning**: Removes ads, standardizes format
    - 🔄 **Translation**: Calls DeepSeek/GPT to translate foreign texts
    - 📝 **Summarization**: Extracts core facts, removes redundancy
    - 🔢 **Vectorization**: Uses Qwen-Embedding to convert news into vectors

#### Step 2: Intelligence Analysis
> When you need intelligence, the brain starts working

- **General Daily**: `NewsAnalyzer` extracts recent 24h news → Clusters by sector → Expert Model analysis → Outputs Markdown Daily Report
- **Investment Analysis**: `InvestmentAnalyzer` → `SimpleAgent` + `investment-report-skill` → Five-Layer Value Investment Framework → Outputs Investment Report
- **Personal Insights**: `InsightGenerator` reads your profile → Retrieves strong relevant news → Generates "Opportunity/Risk" assessment

#### Step 3: Distribution & Management
> Deliver intelligence to users

- **Subscription Management**: Web backend for managing subscribers, report types, and active periods
- **Email Distribution**: Supports SMTP email distribution with dynamic subscription list reading

---

## 🤖 Agent Investment Analysis System

NewsPilot introduces a brand-new **SimpleAgent** architecture for automated investment analysis:

### Key Features

- **Skill-Driven**: Complete analysis workflow defined by `investment-report-skill`
- **Five-Layer Value Investment Framework**: Macro Security → Business Model → Financial Valuation → Industry Logic → Contrarian Risk Control
- **Rich Toolset**: Integrated A-share data, commodity futures, technical indicators, and more
- **Parallel Analysis**: Uses `spawn` to create sub-agents for parallel multi-stock analysis

### Usage Example

```bash
# Generate today's investment report
python -m src.workflows.run_investment_report

# Specify date and model
python -m src.workflows.run_investment_report --date 2026-03-15 --model gemini --max-stocks 8
```

---

## 📋 Subscription Management System

Built-in HTTP subscription management backend supporting:

- Add/Remove subscribers
- Configure report types (General Daily, Zhihu Report, Investment Report, etc.)
- Set active time periods
- Enable/Disable subscriptions

```bash
# Start subscription management backend
python -m src.workflows.run_subscription_admin

# Access http://localhost:18000
```

---

## 🙏 Acknowledgments

This project is made possible by the support of the following excellent foundation models and open-source services:

*   **Core Intelligence**: [Google Gemini](https://ai.google.dev/) (Thinking Model), [OpenAI GPT](https://openai.com/), [DeepSeek](https://www.deepseek.com/) (V3/R1)
*   **Semantic Embedding**: [Qwen (Tongyi Qianwen)](https://tongyi.aliyun.com/) - Provides excellent Chinese semantic vector support
*   **Data Sources**: [NewsAPI](https://newsapi.org/), [Reuters](https://www.reuters.com/), Zhihu
*   **Stock Data**: [akshare](https://www.akshare.xyz/) - China Financial Data Interface Library

---

## ⚠️ License

This project is licensed under the **MIT License**.

You are free to use, modify, and distribute the source code of this project, including for commercial purposes. You only need to include the original author's copyright notice and license notice in the software copy.

**Disclaimer**: The investment suggestions and analysis generated by this system are for reference only and do not constitute actual investment basis. Investment involves risks, proceed with caution.

---

## 🤝 Contribute

NewsPilot is still iterating fast, your participation is very welcome!

*   **Star 🌟**: If you like this project, please click Star in the upper right corner to support it!
*   **Fork & PR**: Welcome to submit code to fix bugs or add new features (such as connecting more news sources, Web UI optimization, etc.).
*   **Issue**: Encounter problems or have new ideas? Please submit an Issue for discussion.

---

## 📬 Contact

*   **Author**: Wang Qiushuo
*   **Email**: 1835886867@qq.com
*   **GitHub**: [NewsPilot Repository](https://github.com/Thislu13/NewsPilot)

---

<div align="center">
  <sub>Generated by NewsPilot Team · 2026</sub>
</div>
