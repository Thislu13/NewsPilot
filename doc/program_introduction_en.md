<!--
 * @Author: WangQiushuo 185886867@qq.com
 * @Date: 2026-02-08
 * @FilePath: \code\NewsPilot\program_introduction.md
 * @Description: NewsPilot System Architecture Documentation
 *
 * Copyright (c) 2026, All Rights Reserved.
-->

# NewsPilot System Architecture (V0.2)

## 1. Project Overview

NewsPilot is a modular intelligent news analysis system designed to automate the acquisition, processing, and semantic understanding of global news. The system supports multiple core operational modes:

- **General Daily Reports**: Professional industry research reports
- **Investment Analysis**: Automated value investment analysis based on Agent + Skill architecture
- **Zhihu Hot Topics Tracking**: Social media content acquisition and analysis
- **Personalized Insights**: Customized intelligence based on user profiles

---

## 2. Directory Structure

```text
NewsPilot/
├── README.md                       # Project overview
├── requirements.txt                # Python dependencies
├── config/                         # [Configuration Center]
│   ├── keys.py                     # API keys and credentials
│   ├── prompts.py                  # LLM prompt library
│   ├── settings.py                 # System general configuration
│   ├── workflow_service.json       # Service runtime configuration
│   ├── zhihu_user_config.py        # Zhihu user configuration
│   └── docker/                     # Docker composition files
│
├── core/                           # [Domain Core]
│   ├── news_schemas.py             # Data models (Pydantic Schemas)
│   └── user_schemas.py             # User profile & preference models
│
├── data/                           # [Data Storage]
│   ├── daily_reports/              # Generated markdown daily reports
│   │   └── YYYY-MM-DD/
│   │       ├── markdown/           # Domain-specific reports
│   │       └── investment/         # Investment analysis reports
│   └── personal_report/            # Personalized user insights
│
├── doc/                            # [Documentation]
│   ├── program_introduction_cn.md  # Architecture doc (Chinese)
│   ├── program_introduction_en.md  # Architecture doc (English)
│   └── README_en.md                # Project overview (English)
│
└── src/                            # [Source Code]
    │
    ├── admin/                      # [Admin Backend]
    │   ├── subscription_admin_server.py  # HTTP subscription management
    │   └── static/                 # Frontend static files
    │
    ├── custom_logging/             # [Logging System]
    │   └── logging_config.py       # Unified logging configuration
    │
    ├── data_acquisition/           # [Data Layer] (ELT Pipeline)
    │   ├── daemon_orchestrator.py  # [Async] Long-running service manager
    │   ├── orchestrator.py         # [Sync] On-demand acquisition orchestrator
    │   ├── zhihu_daemon_orchestrator.py  # Zhihu acquisition daemon
    │   ├── fetchers/               # Data source adapters
    │   │   ├── base_fetcher.py
    │   │   ├── newsapi_fetcher.py
    │   │   ├── rsshub_fetcher.py
    │   │   ├── reuters_fetcher.py
    │   │   └── zhihu_fetcher.py
    │   ├── processors/             # Processing pipeline
    │   │   ├── pipeline.py
    │   │   └── module/
    │   │       ├── translator.py   # Translation
    │   │       ├── summarizer.py   # Summarization
    │   │       ├── embedding.py    # Vectorization
    │   │       └── normalize.py    # Cleaning
    │   └── module/                 # Low-level crawler tools
    │       ├── download.py
    │       ├── get_content.py
    │       └── paser_html.py
    │
    ├── distribution/               # [Distribution Layer]
    │   ├── email_sender.py         # Email sending
    │   └── recipient_provider.py   # Subscriber management
    │
    ├── intelligence/               # [AI Layer]
    │   ├── new_analyzer.py         # General daily report engine
    │   ├── investment_analyzer.py  # Investment analysis engine (Agent-based)
    │   ├── insight_generator.py    # Personalized insight engine
    │   ├── zhihu_analyzer.py       # Zhihu content analysis engine
    │   └── renderers/              # Report renderers
    │       ├── daily_report.py
    │       ├── daily_total_report.py
    │       └── zhihu_report/
    │
    ├── module/                     # [Infrastructure]
    │   ├── init_client.py          # LLM client factory
    │   ├── content_converter.py    # Content conversion utilities
    │   ├── utils.py                # General utilities
    │   └── agent/                  # [Agent System]
    │       ├── simple_agent.py     # Core Agent implementation
    │       ├── context.py          # Context management
    │       ├── providers/          # LLM provider adapters
    │       │   ├── base.py
    │       │   └── litellm_provider.py
    │       ├── tools/              # Tool registry & implementations
    │       │   ├── registry.py
    │       │   ├── stock_data.py   # A-Share data tools
    │       │   ├── stock_market.py # Market data tools
    │       │   ├── commodity_data.py  # Commodity futures tools
    │       │   ├── filesystem.py   # Filesystem tools
    │       │   ├── shell.py        # Command execution tools
    │       │   ├── web.py          # Web search/fetch tools
    │       │   └── spawn.py        # Sub-agent tool
    │       └── skills/             # Skill system
    │           ├── loader.py       # Skill loader
    │           ├── value-investment-strategy/  # Value investment framework
    │           └── investment-report-skill/    # Investment report generation
    │
    ├── storage/                    # [Persistence Layer]
    │   ├── models.py               # SQL Alchemy ORM Models
    │   ├── repository.py           # Database repository pattern
    │   ├── subscription_repository.py  # Subscription data management
    │   └── db_config.py            # Database connection setup
    │
    └── workflows/                  # [Entry Points]
        ├── run_service.py          # Unified service entry
        ├── run_news_service.py     # News acquisition service
        ├── run_daily_report.py     # General daily report generation
        ├── run_investment_report.py    # Investment report generation
        ├── run_subscription_admin.py   # Subscription admin backend
        ├── main_pipeline.py        # Personalized analysis pipeline
        └── zhihu_ananlysis_service/    # Zhihu analysis service
            ├── service.py
            ├── worker.py
            └── run_zhihu_analysis_service.py
```

---

## 3. Core Architecture

The system follows a **Layered Architecture**, decoupling **Data Production**, **Intelligence Consumption**, and **Distribution Management**.

### 3.1 Infrastructure Layer

#### A. News Acquisition Service
Responsible for building a high-quality, continuous knowledge base of global news.

*   **Entry Point**: `src/workflows/run_news_service.py`
*   **Operational Mode**: Daemon service (long-running)
*   **Component**: `DaemonOrchestrator` (`src/data_acquisition/daemon_orchestrator.py`)
*   **Workflow**:
    1.  **Acquisition Job**: Periodically fetches raw data using adapters in `fetchers/`
    2.  **Processing Pipeline**: Applies cleaning, translation (LLM), summarization (LLM), and vector embedding
    3.  **Storage**: Persists refined data into PostgreSQL (with pgvector support)

#### B. Zhihu Acquisition Service
Focused on content acquisition and analysis from Zhihu platform.

*   **Entry Point**: `src/workflows/zhihu_ananlysis_service/run_zhihu_analysis_service.py`
*   **Components**: `ZhihuDaemonOrchestrator`, `ZhihuProcessingWorker`
*   **Function**: Acquires Zhihu trending content and generates structured hotspot reports

### 3.2 Agent Intelligence Layer

> New architecture introduced in V0.2, based on SimpleAgent + Skill system

#### SimpleAgent Architecture

```
┌─────────────────────────────────────────┐
│           SimpleAgent                   │
│  ┌─────────────────────────────────┐    │
│  │  LLM Provider (LiteLLM)         │    │
│  │  - gemini/deepseek/qwen         │    │
│  └─────────────────────────────────┘    │
│  ┌─────────────────────────────────┐    │
│  │  Tool Registry                  │    │
│  │  • Stock Data (akshare)         │    │
│  │  • Commodity Futures            │    │
│  │  • Filesystem (read/list)       │    │
│  │  • Web Search/Fetch             │    │
│  │  • Sub-agent Spawn              │    │
│  └─────────────────────────────────┘    │
│  ┌─────────────────────────────────┐    │
│  │  Skill System                   │    │
│  │  • value-investment-strategy    │    │
│  │  • investment-report-skill      │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

#### Investment Analysis Workflow

1. **Skill Loading**: `investment-report-skill` defines the complete analysis workflow
2. **News Reading**: Agent automatically reads daily reports from various domains
3. **Stock Identification**: Identifies 5-8 potential investment targets
4. **Parallel Analysis**: Uses `spawn` to create sub-agents for parallel deep analysis
5. **Value Investment Framework**: Each sub-agent uses `value-investment-strategy` skill:
    - Layer 1: Macro Security Filter (Five Major Security Themes)
    - Layer 2: Business Model Assessment ("Demand" Theory)
    - Layer 3: Financial Analysis & Valuation (PE/PB/Cash Flow/Dividend)
    - Layer 4: Industry-Specific Logic (Non-ferrous/Banking/Coal Chemical, etc.)
    - Layer 5: Contrarian Risk Control (Crowd Sentiment Test)
6. **Report Generation**: Aggregates analysis results and generates structured investment daily report

### 3.3 Application Layer

#### A. General Intelligence (Daily Reports)
*   **Entry Point**: `src/workflows/run_daily_report.py`
*   **Engine**: `NewsAnalyzer` (`src/intelligence/new_analyzer.py`)
*   **Scenario**: Scheduled task (e.g., Daily at 8:00 AM)
*   **Logic**: Aggregates news from the last 24 hours, categorizes by sector, uses "Expert Outlook" model to generate structured reports

#### B. Investment Intelligence (Investment Reports)
*   **Entry Point**: `src/workflows/run_investment_report.py`
*   **Engine**: `InvestmentAnalyzer` (`src/intelligence/investment_analyzer.py`)
*   **Dependencies**: `SimpleAgent` + `investment-report-skill`
*   **Scenario**: Automated investment analysis based on value investment framework

#### C. Personalized Intelligence (User Insights)
*   **Entry Point**: `src/workflows/main_pipeline.py`
*   **Engine**: `InsightGenerator` (`src/intelligence/insight_generator.py`)
*   **Scenario**: On-demand or user-triggered
*   **Logic**: Loads user profile (holdings, interests, risk tolerance) and generates exclusive insights

### 3.4 Distribution Management Layer

#### Subscription Management System
*   **Entry**: `src/workflows/run_subscription_admin.py`
*   **Function**: HTTP Web backend for managing subscribers
*   **Data Table**: `subscription_targets` stores subscriber information

#### Email Distribution
*   **Component**: `EmailSender` (`src/distribution/email_sender.py`)
*   **Function**: Supports SMTP email distribution, dynamically reads subscription list

---

## 4. Key Technical Components

### 4.1 Data Layer (`src/data_acquisition`)
*   **Fetchers**: Modular adapters supporting multiple news sources
*   **Processors**: Pipeline architecture (`pipeline.py`) orchestrating translation, summarization, and vectorization

### 4.2 Agent Layer (`src/module/agent`)
*   **SimpleAgent**: Core Agent implementation with tool calling and sub-agent creation
*   **LiteLLM Provider**: Unified interface supporting Gemini/DeepSeek/Qwen models
*   **Tool Registry**: Dynamic tool registration and management
*   **Skill Loader**: Markdown-based extensible Skill framework

### 4.3 Tool Set (`src/module/agent/tools`)
| Tool | Function | Data Source |
|-----|------|--------|
| `A_Stock_Profile` | A-Share stock fundamentals | akshare |
| `A_Stock_Price_History` | Historical price data | akshare |
| `A_Stock_Technical_Indicators` | Technical indicators | akshare |
| `Commodity_Futures_Basis_Overview` | Commodity futures basis | akshare |
| `Commodity_Inventory_Or_Receipt` | Inventory/Warrant data | akshare |
| `WebSearch/WebFetch` | Web search and fetch | Brave API |
| `Spawn` | Create Sub-agent | - |

### 4.4 Storage Layer (`src/storage`)
*   **Repository Pattern**: Abstracts database interactions
*   **SubscriptionRepository**: Dedicated repository for subscription management
*   **pgvector**: Supports vector storage and semantic retrieval

---

## 5. Operation Modes

### 5.1 Service Mode (Recommended for Production)

```bash
# Unified entry, configured via workflow_service.json
python -m src.workflows.run_service

# Start news acquisition service separately
python -m src.workflows.run_news_service

# Start Zhihu acquisition service separately
python -m src.workflows.zhihu_ananlysis_service.run_zhihu_analysis_service

# Start subscription management backend
python -m src.workflows.run_subscription_admin
```

### 5.2 Task Mode (Recommended for Scheduled Jobs)

```bash
# Generate general daily report
python -m src.workflows.run_daily_report

# Generate investment report
python -m src.workflows.run_investment_report --date 2026-03-15

# Generate personalized insights
python -m src.workflows.main_pipeline
```

---

## 6. Release Status (V0.2)

### New Features in V0.2
*   **Agent Investment Analysis System**: Automated value investment analysis based on SimpleAgent + Skill
*   **Zhihu Hot Topics Tracking**: New Zhihu content acquisition and analysis service
*   **Subscription Management System**: Web backend for managing subscribers and distribution configuration
*   **Skill System**: Markdown-based extensible Skill framework
*   **Multi-Model Support**: Unified access to Gemini/DeepSeek/Qwen via LiteLLM

### Capabilities
*   Full-stack automation from acquisition to analysis
*   Dual-mode operation (background service + on-demand reports)
*   Agent-driven intelligent investment analysis
*   Flexible subscription management and distribution

### Infrastructure
*   PostgreSQL + pgvector
*   Docker containerization support
*   Unified logging system

---

*Last updated: 2026-03-15*
