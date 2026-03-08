"""Simple Agent for single-call execution."""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from src.module.agent.context import SimpleContextBuilder
from src.module.agent.providers.base import LLMProvider
from src.module.agent.tools import (
    # EditFileTool,  # 已禁用
    ExecTool,
    ListDirTool,
    ReadFileTool,
    SpawnTool,
    ToolRegistry,
    WebFetchTool,
    WebSearchTool,
    # WriteFileTool,  # 已禁用
    A_Stock_Profile,
    A_Stock_Price_History,
    A_Stock_Technical_Indicators,
    A_Stock_Market_Overview,
    Commodity_Futures_Basis_Overview,
    Commodity_Inventory_Or_Receipt,
    Commodity_Position_Rank_Summary,
)


class SimpleAgent:
    """
    Complete single-call agent implementation.

    Features:
    - LLM interaction with tool calling
    - Skills loading
    - Tools execution (filesystem, shell, web)
    - Sub-agent spawning
    - MCP extensions (optional)

    Removed:
    - Memory/session management
    - Multi-channel communication
    - Message bus
    """

    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        brave_api_key: str | None = None,
        exec_timeout: int = 120,
        restrict_to_workspace: bool = False,
        enable_spawn: bool = True,
    ):
        """
        Initialize SimpleAgent.

        Args:
            provider: LLM provider instance
            workspace: Workspace directory path
            model: Model name (if None, uses provider's default)
            max_iterations: Maximum tool call iterations
            temperature: LLM temperature
            max_tokens: Maximum tokens per response
            brave_api_key: API key for web search
            exec_timeout: Shell command timeout in seconds
            restrict_to_workspace: Restrict file operations to workspace
            enable_spawn: Enable sub-agent spawning
        """
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enable_spawn = enable_spawn

        # Context builder (with skills, no memory)
        self.context = SimpleContextBuilder(workspace)

        # Tool registry
        self.tools = ToolRegistry()
        self._register_default_tools(brave_api_key, exec_timeout, restrict_to_workspace)

    def _register_default_tools(
        self,
        brave_api_key: str | None,
        exec_timeout: int,
        restrict_to_workspace: bool,
    ) -> None:
        """Register default tools."""
        allowed_dir = self.workspace if restrict_to_workspace else None

        # Filesystem tools
        self.tools.register(ReadFileTool(self.workspace, allowed_dir))
        # self.tools.register(WriteFileTool(self.workspace, allowed_dir))  # 禁用写入功能
        # self.tools.register(EditFileTool(self.workspace, allowed_dir))  # 禁用编辑功能
        self.tools.register(ListDirTool(self.workspace, allowed_dir))

        # Shell tool
        self.tools.register(
            ExecTool(
                working_dir=str(self.workspace),
                timeout=exec_timeout,
                restrict_to_workspace=restrict_to_workspace,
            )
        )

        # Web tools
        if brave_api_key:
            self.tools.register(WebSearchTool(api_key=brave_api_key))
        self.tools.register(WebFetchTool())

        # Custom stock data tools
        self.tools.register(A_Stock_Profile())
        self.tools.register(A_Stock_Price_History())
        self.tools.register(A_Stock_Technical_Indicators())
        self.tools.register(A_Stock_Market_Overview())

        # Custom commodity data tools
        self.tools.register(Commodity_Futures_Basis_Overview())
        self.tools.register(Commodity_Inventory_Or_Receipt())
        self.tools.register(Commodity_Position_Rank_Summary())

        # Sub-agent tool
        if self.enable_spawn:
            self.tools.register(SpawnTool(agent_factory=self._create_sub_agent))

    async def _create_sub_agent(self, max_iterations: int = 20):
        """
        Create a sub-agent for handling subtasks.

        Args:
            max_iterations: Max iterations for sub-agent

        Returns:
            SimpleAgent instance
        """
        return SimpleAgent(
            provider=self.provider,
            workspace=self.workspace,
            model=self.model,
            max_iterations=max_iterations,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            enable_spawn=False,  # Prevent infinite recursion
        )

    async def _run_agent_loop(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """
        Run the agent iteration loop with tool calls.

        Args:
            messages: Initial message list

        Returns:
            Tuple of (final_content, all_messages)
        """
        iteration = 0
        final_content = None

        while iteration < self.max_iterations:
            iteration += 1

            # Call LLM
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            # Handle tool calls
            if response.has_tool_calls:
                # Add assistant message with tool calls
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ]

                messages.append(
                    {
                        "role": "assistant",
                        "content": response.content,
                        "tool_calls": tool_call_dicts,
                    }
                )

                # Execute tools
                for tool_call in response.tool_calls:
                    logger.info(
                        f"Tool call: {tool_call.name}({json.dumps(tool_call.arguments, ensure_ascii=False)[:200]})"
                    )
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)

                    # Add tool result
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "content": result,
                        }
                    )
            else:
                # No more tool calls, we're done
                final_content = response.content
                break

        if final_content is None and iteration >= self.max_iterations:
            logger.warning(f"Max iterations ({self.max_iterations}) reached")
            final_content = (
                f"达到最大迭代次数 ({self.max_iterations}),任务未完成。"
                "请尝试将任务分解为更小的步骤。"
            )

        return final_content, messages

    async def ask(self, question: str, skill_names: list[str] | None = None) -> str:
        """
        Single-call interface to ask the agent a question.

        Args:
            question: The question/task to ask
            skill_names: Optional list of skill names to include

        Returns:
            Agent's response as string
        """
        # Build system prompt (with skills, no memory)
        system_prompt = self.context.build_system_prompt(skill_names)

        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

        # Run agent loop
        final_content, _ = await self._run_agent_loop(messages)

        return final_content or "无响应"

    async def close(self) -> None:
        """Close and cleanup resources."""
        logger.info("SimpleAgent closed")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
