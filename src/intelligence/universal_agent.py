"""
通用 Agent - 配置驱动的多领域分析Agent

通过 Skills + Tools + Prompt模板 实现领域差异化，
避免为每个领域创建单独的Agent类。

Usage:
    from src.intelligence.universal_agent import UniversalAgent

    # 投资分析
    agent = UniversalAgent(
        model_name="gemini",
        skills=["value-investment"],
        prompt_template="investment"
    )
    result = await agent.analyze("分析铜行业投资机会")

    # 科研分析（同一个类，不同配置）
    agent = UniversalAgent(
        model_name="gemini",
        skills=["trend-analysis"],
        prompt_template="research"
    )
    result = await agent.analyze("追踪大模型技术发展趋势")
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Callable
from pathlib import Path

from src.module.init_client import LLMClientFactory
from src.module.agent import AgentLoop
from src.module.agent.tools import (
    BaseTool, ToolResult, ToolRegistry,
    FetchNewsTool, SearchNewsTool,
    StockQuoteTool, MarketIndexTool, StockFundamentalsTool, IndustryDataTool,
    MCPManager
)
from src.storage.repository import StorageRepository

# 导入Prompt模板
try:
    from config.prompts import (
        VALUE_INVESTMENT_PROMPT,
        GROWTH_INVESTMENT_PROMPT,
        DEFAULT_ANALYSIS_PROMPT,
    )
    PROMPTS_AVAILABLE = True
except ImportError:
    PROMPTS_AVAILABLE = False
    print("[!] Warning: config.prompts not available, using default prompts")


class UniversalAgent:
    """
    通用Agent - 通过配置实现领域差异化

    设计原则：
    1. 单一Agent类，配置驱动
    2. Skills定义分析框架
    3. Tools提供数据获取能力
    4. Prompt模板控制输出格式

    特点：
    - 支持多种Skill组合
    - 支持自定义工具
    - 支持MCP集成
    - 支持多轮推理
    - 运行时可切换配置

    Args:
        model_name: LLM模型名称 (gemini/deepseek/qwen)
        skills: Skill列表，如 ["value-investment", "risk-management"]
        prompt_template: Prompt模板名称 ("investment"/"research"/"default")
        tools: 自定义工具列表
        mcp_servers: MCP服务器配置
        max_iterations: 最大迭代次数
        temperature: LLM温度参数
    """

    # Prompt模板映射
    PROMPT_TEMPLATES = {
        "investment": "投资分析Agent",
        "research": "科研分析Agent",
        "default": "通用分析Agent"
    }

    def __init__(
        self,
        model_name: str = "gemini",
        skills: Optional[List[str]] = None,
        prompt_template: str = "default",
        tools: Optional[List[BaseTool]] = None,
        mcp_servers: Optional[Dict[str, Dict]] = None,
        max_iterations: int = 10,
        temperature: float = 0.7,
    ):
        """
        初始化通用Agent

        Args:
            model_name: LLM模型名称
            skills: Skill列表
            prompt_template: Prompt模板名称
            tools: 自定义工具列表
            mcp_servers: MCP服务器配置
            max_iterations: 最大迭代次数
            temperature: LLM温度
        """
        self.model_name = model_name
        self.prompt_template = prompt_template
        self.factory = LLMClientFactory()
        self.repo = StorageRepository()
        self.mcp_servers = mcp_servers

        # Get LLM client
        self.client = self.factory.get_client(model_name)

        # Skills配置
        self.skills = skills or []

        # 创建工具注册表
        self.tool_registry = ToolRegistry()

        # 注册内置工具（根据prompt_template决定）
        self._register_builtin_tools()

        # 注册自定义工具
        if tools:
            for tool in tools:
                self.tool_registry.register(tool)

        # 构建Identity（基于prompt_template和skills）
        identity = self._build_identity()

        # 创建Agent Loop
        self.agent = AgentLoop(
            provider=self.client,
            tools=list(self.tool_registry._tools.values()),
            skills=self.skills,
            identity=identity,
            max_iterations=max_iterations,
            temperature=temperature,
            max_tokens=8192,
            memory_window=5,
        )

        # MCP manager
        self._mcp_manager: Optional[MCPManager] = None

        print(f"[*] UniversalAgent initialized [model={model_name}, template={prompt_template}, skills={self.skills}]")

    def _register_builtin_tools(self):
        """
        注册内置工具

        根据prompt_template决定注册哪些工具
        """
        # 投资分析相关工具
        if self.prompt_template == "investment":
            builtin_tools = [
                FetchNewsTool(self.repo),
                SearchNewsTool(self.repo),
                StockQuoteTool(),
                MarketIndexTool(),
                StockFundamentalsTool(),
                IndustryDataTool(),
            ]
        # 科研分析相关工具
        elif self.prompt_template == "research":
            builtin_tools = [
                FetchNewsTool(self.repo),
                SearchNewsTool(self.repo),
                # 可以添加论文搜索、引用分析等工具
            ]
        # 默认工具集
        else:
            builtin_tools = [
                FetchNewsTool(self.repo),
                SearchNewsTool(self.repo),
            ]

        for tool in builtin_tools:
            self.tool_registry.register(tool)

    def _build_identity(self) -> str:
        """
        构建Agent身份

        基于prompt_template和skills动态生成
        """
        if self.prompt_template == "investment":
            if PROMPTS_AVAILABLE:
                # 使用config/prompts中的Prompt
                base_prompt = VALUE_INVESTMENT_PROMPT if "value" in str(self.skills) else GROWTH_INVESTMENT_PROMPT
                # 提取框架部分作为identity
                identity = f"""你是一个专业的投资分析师。

可用工具：
- fetch_news: 获取新闻数据
- search_news: 搜索新闻
- get_stock_quote: 获取股票行情
- get_market_index: 获取市场指数
- get_stock_fundamentals: 获取基本面数据
- get_industry_data: 获取行业数据

分析框架将由Skill提供。

输出要求：
- 结构化分析报告
- 具体可执行的建议
- 明确的风险提示
- 量化指标支持
"""
            else:
                # 回退到默认Prompt
                identity = """你是一个专业的投资分析师。

可用工具：
- fetch_news: 获取新闻数据
- search_news: 搜索新闻
- get_stock_quote: 获取股票行情

分析框架将由Skill提供。
"""

        elif self.prompt_template == "research":
            identity = """你是一个科研趋势分析师。

可用工具：
- fetch_news: 获取新闻数据
- search_news: 搜索新闻

分析框架将由Skill提供。

输出要求：
- 技术突破分析
- 发展趋势判断
- 研究方向建议
"""

        else:
            identity = """你是一个通用分析助手。

可用工具：
- fetch_news: 获取新闻数据
- search_news: 搜索新闻

分析框架将由Skill提供。
"""

        return identity

    async def connect_mcp(self, servers_config: Optional[Dict[str, Dict]] = None):
        """
        连接MCP服务器并注册MCP工具

        Args:
            servers_config: MCP服务器配置，如果为None则使用self.mcp_servers
        """
        config = servers_config or self.mcp_servers
        if not config:
            print("[!] No MCP servers configured")
            return

        self._mcp_manager = MCPManager()
        mcp_tools = await self._mcp_manager.connect(config)

        # 注册MCP工具
        for tool in mcp_tools:
            self.tool_registry.register(tool)
            # 重建agent的工具列表
            self.agent.tools = list(self.tool_registry._tools.values())

        print(f"[*] MCP connected: {len(mcp_tools)} tools registered")

    async def disconnect_mcp(self):
        """断开MCP连接"""
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
        执行分析任务

        Args:
            query: 用户查询
            on_progress: 进度回调函数

        Returns:
            AgentResponse with analysis content
        """
        print(f"[*] Starting analysis: {query}")

        result = await self.agent.run_once(query, on_progress=on_progress)

        print(f"[*] Analysis completed. Iterations: {result.iteration_count}")
        print(f"[*] Tools used: {result.tools_used}")

        return result

    async def analyze_with_daily_report(
        self,
        report_date: Optional[datetime] = None,
        query: str = "分析投资机会"
    ) -> Any:
        """
        基于新闻日报进行分析

        Args:
            report_date: 日报日期，默认今天
            query: 分析查询

        Returns:
            AgentResponse
        """
        # TODO: 实现日报获取逻辑
        # daily_report = await self._fetch_daily_report(report_date)

        # 暂时使用新闻获取
        if report_date is None:
            report_date = datetime.now()

        start_time = report_date.replace(hour=0, minute=0, second=0)
        end_time = report_date.replace(hour=23, minute=59, second=59)

        enhanced_query = f"""基于 {start_time.strftime('%Y-%m-%d')} 的新闻数据，{query}

请执行以下步骤：
1. 使用 fetch_news 工具获取相关新闻
2. 分析新闻内容
3. 运用分析框架进行独立分析
4. 给出具体建议

注意：新闻是客观事实，你的分析基于所选框架。
"""

        return await self.analyze(enhanced_query)

    def save_report(
        self,
        content: str,
        output_path: str,
        metadata: Optional[Dict] = None
    ):
        """
        保存分析报告

        Args:
            content: 报告内容
            output_path: 输出路径
            metadata: 元数据（时间范围、模型等）
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        metadata = metadata or {}
        header = f"""# 分析报告 ({self.PROMPT_TEMPLATES.get(self.prompt_template, 'Unknown')})

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**使用模型**: {self.model_name}
**使用Skill**: {', '.join(self.skills) if self.skills else 'None'}
**模板类型**: {self.prompt_template}

---

"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header + content)

        print(f"[✓] Report saved to: {output_path}")

    def clear_history(self):
        """清除对话历史"""
        self.agent.clear_history()


# 向后兼容：InvestmentAgent 作为 UniversalAgent 的别名
class InvestmentAgent(UniversalAgent):
    """
    投资分析Agent（向后兼容）

    这是UniversalAgent的一个预配置版本，
    默认使用投资分析相关的配置。

    Usage:
        agent = InvestmentAgent(model_name="gemini")
        result = await agent.analyze("分析铜行业投资机会")
    """

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
        初始化投资分析Agent

        Args:
            model_name: LLM模型名称
            skills: Skill列表，默认 ["investment-strategy-skill"]
            max_iterations: 最大迭代次数
            temperature: LLM温度
            mcp_servers: MCP服务器配置
            custom_tools: 自定义工具列表
        """
        # 默认使用投资相关的skill
        if skills is None:
            skills = ["investment-strategy-skill"]

        super().__init__(
            model_name=model_name,
            skills=skills,
            prompt_template="investment",
            tools=custom_tools,
            mcp_servers=mcp_servers,
            max_iterations=max_iterations,
            temperature=temperature,
        )

    async def analyze_with_news(
        self,
        time_range: Optional[tuple] = None,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        基于新闻进行投资分析（向后兼容方法）

        Args:
            time_range: (start, end) datetime tuple
            output_path: 报告输出路径

        Returns:
            分析结果字典
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

        # 保存报告
        if output_path and result.content:
            self.save_report(
                result.content,
                output_path,
                metadata={"time_range": time_range}
            )

        return {
            "status": "success" if result.content else "error",
            "content": result.content,
            "tools_used": result.tools_used,
            "iteration_count": result.iteration_count,
            "output_path": output_path
        }
