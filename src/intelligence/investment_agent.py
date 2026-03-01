"""
投资分析 Agent - 使用 Agent 架构进行智能选股分析

整合 nanobot agent 能力和 NewsPilot 的新闻数据，
提供智能化的投资分析服务。

Usage:
    from src.intelligence.investment_agent import InvestmentAgent

    agent = InvestmentAgent(model_name="gemini")

    result = await agent.analyze("基于最近的新闻，分析铜行业的投资机会")
    print(result.content)
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Callable

from src.module.init_client import LLMClientFactory
from src.module.agent import AgentLoop
from src.module.agent.tools import (
    BaseTool, ToolResult, ToolRegistry,
    FetchNewsTool, SearchNewsTool,
    StockQuoteTool, MarketIndexTool, StockFundamentalsTool, IndustryDataTool,
    MCPManager
)
from src.storage.repository import StorageRepository


class InvestmentAgent:
    """
    投资分析 Agent - 基于 Agent 架构的智能选股分析器

    特点：
    1. 使用 investment-strategy-skill 作为知识体系
    2. 支持工具调用（获取新闻、搜索股票等）
    3. 支持 MCP (Model Context Protocol) 集成
    4. 支持自定义工具
    5. 支持多轮推理
    6. 生成结构化的投资分析报告

    Usage:
        # 基础用法
        agent = InvestmentAgent(model_name="gemini")
        result = await agent.analyze("分析铜行业投资机会")

        # 使用 MCP
        mcp_servers = {
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"]
            }
        }
        agent = InvestmentAgent(model_name="gemini", mcp_servers=mcp_servers)

        # 添加自定义工具
        from src.module.agent.tools.custom import MyCustomTool
        agent = InvestmentAgent(model_name="gemini", custom_tools=[MyCustomTool()])
    """

    # Agent 身份定义
    IDENTITY = """你是一个专业的投资分析师，具备深度价值投资选股能力。

你的职责是：
1. 基于新闻信息识别投资机会
2. 运用深度价值投资框架进行分析
3. 给出具体的投资建议和行动计划

可用工具：
- fetch_news: 获取新闻数据
- search_news: 搜索新闻
- get_stock_quote: 获取股票行情
- get_market_index: 获取市场指数
- get_stock_fundamentals: 获取基本面数据
- get_industry_data: 获取行业数据

分析框架：
1. 宏观安全过滤 - 识别五大安全主题（粮食/金融/科技/资源/能源）
2. 商业模式鉴定 - 评估"求"级别（三求/两求/一求/零求）
3. 财务与估值 - 分析PE、PB、股息率等指标
4. 行业差异化 - 根据行业特点进行选股
5. 逆向情绪风控 - 避免追高、注意 liquidity 风险

输出要求：
- 结构化分析报告
- 具体可执行的建议
- 明确的风险提示
- 量化指标支持

记住：模糊的正确远胜于精确的错误。抓住核心变量，不要在会计科目里游泳。"""

    def __init__(
        self,
        model_name: str = "gemini",
        skills: Optional[List[str]] = None,
        max_iterations: int = 10,
        temperature: float = 0.7,
        mcp_servers: Optional[Dict[str, Dict]] = None,
        custom_tools: Optional[List[BaseTool]] = None,
    ):
        """
        Initialize the investment agent.

        Args:
            model_name: LLM model name (gemini/deepseek/qwen)
            skills: List of skill names to load (default: investment-strategy-skill)
            max_iterations: Maximum tool call iterations
            temperature: LLM temperature
            mcp_servers: MCP server configurations
            custom_tools: List of custom tools to add
        """
        self.model_name = model_name
        self.factory = LLMClientFactory()
        self.repo = StorageRepository()
        self.mcp_servers = mcp_servers

        # Get LLM client
        self.client = self.factory.get_client(model_name)

        # Default skills
        self.skills = skills or ["investment-strategy-skill"]

        # Create tools registry
        self.tools = ToolRegistry()

        # Register built-in tools
        self._register_builtin_tools()

        # Register custom tools
        if custom_tools:
            for tool in custom_tools:
                self.tools.register(tool)

        # Create agent loop
        self.agent = AgentLoop(
            provider=self.client,
            tools=list(self.tools._tools.values()),
            skills=self.skills,
            identity=self.IDENTITY,
            max_iterations=max_iterations,
            temperature=temperature,
            max_tokens=8192,
            memory_window=5,
        )

        # MCP manager (initialized lazily)
        self._mcp_manager: Optional[MCPManager] = None

        print(f"[*] InvestmentAgent initialized [model={model_name}, skills={self.skills}]")

    def _register_builtin_tools(self):
        """Register built-in tools."""
        builtin_tools = [
            FetchNewsTool(self.repo),
            SearchNewsTool(self.repo),
            StockQuoteTool(),
            MarketIndexTool(),
            StockFundamentalsTool(),
            IndustryDataTool(),
        ]

        for tool in builtin_tools:
            self.tools.register(tool)

    async def connect_mcp(self, servers_config: Optional[Dict[str, Dict]] = None):
        """
        Connect to MCP servers and register MCP tools.

        Args:
            servers_config: MCP server configurations. If None, uses self.mcp_servers.
        """
        config = servers_config or self.mcp_servers
        if not config:
            print("[!] No MCP servers configured")
            return

        self._mcp_manager = MCPManager()
        mcp_tools = await self._mcp_manager.connect(config)

        # Register MCP tools to agent
        for tool in mcp_tools:
            self.tools.register(tool)
            # Rebuild agent with new tools
            self.agent.tools = self.tools

        print(f"[*] MCP connected: {len(mcp_tools)} tools registered")

    async def disconnect_mcp(self):
        """Disconnect from MCP servers."""
        if self._mcp_manager:
            await self._mcp_manager.disconnect()
            self._mcp_manager = None
            print("[*] MCP disconnected")

    async def analyze(
        self,
        query: str,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> Any:
        """
        Analyze investment opportunities based on the query.

        Args:
            query: User's analysis request
            on_progress: Optional callback for progress updates

        Returns:
            AgentResponse with analysis content
        """
        print(f"[*] Starting investment analysis: {query}")

        result = await self.agent.run_once(query, on_progress=on_progress)

        print(f"[*] Analysis completed. Iterations: {result.iteration_count}")
        print(f"[*] Tools used: {result.tools_used}")

        return result

    async def analyze_with_news(
        self,
        time_range: Optional[tuple] = None,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze investment opportunities from recent news.

        This is a convenience method that automatically fetches news
        and generates a comprehensive analysis report.

        Args:
            time_range: (start, end) datetime tuple, default last 24 hours
            output_path: Optional path to save the report

        Returns:
            Dict with analysis results
        """
        if time_range is None:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=24)
            time_range = (start_time, end_time)

        query = f"""基于 {time_range[0].strftime('%Y-%m-%d %H:%M')} 至 {time_range[1].strftime('%Y-%m-%d %H:%M')} 的新闻数据，
                    进行全面的投资机会分析。

                    请执行以下步骤：
                    1. 使用 fetch_news 工具获取相关新闻
                    2. 分析新闻内容，识别涉及的安全主题和行业
                    3. 运用深度价值投资框架进行分析
                    4. 给出具体的投资建议和行动计划

                    输出要求：
                    - 宏观安全主题分析
                    - 重点行业/标的评估
                    - 投资建议（买入/观望/规避）
                    - 风险提示
                    - 行动计划（具体可执行）
                    """

        result = await self.analyze(query)

        # Save to file if requested
        if output_path and result.content:
            self._save_report(result.content, output_path, time_range)

        return {
            "status": "success" if result.content else "error",
            "content": result.content,
            "tools_used": result.tools_used,
            "iteration_count": result.iteration_count,
            "output_path": output_path
        }

    def _save_report(
        self,
        content: str,
        output_path: str,
        time_range: tuple
    ):
        """Save the analysis report to file."""
        import os

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        header = f"""# 投资策略分析报告 (Agent)

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**分析时间范围**: {time_range[0].strftime('%Y-%m-%d %H:%M')} - {time_range[1].strftime('%Y-%m-%d %H:%M')}
**使用模型**: {self.model_name}
**使用Skill**: {', '.join(self.skills)}

---

"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header + content)

        print(f"[✓] Report saved to: {output_path}")

    def clear_history(self):
        """Clear conversation history."""
        self.agent.clear_history()
