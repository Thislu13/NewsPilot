"""
Agent Loop - 核心处理引擎
从 nanobot 移植并适配到 NewsPilot

Usage:
    # 创建 AgentLoop 实例
    agent = AgentLoop(
        provider=llm_provider,
        tools=[StockSearchTool(), NewsFetchTool()],
        skills=["investment-strategy-skill"],
        identity="你是一个专业的投资分析师..."
    )

    # 运行一次分析
    result = await agent.run_once("基于最近的新闻，分析铜行业投资机会")
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from .context import AgentContextBuilder
from .skills import SkillsLoader
from .tools import ToolRegistry, BaseTool


@dataclass
class ToolCallRequest:
    """A tool call request from the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class AgentResponse:
    """Response from the agent."""
    content: Optional[str] = None
    tool_calls: List[ToolCallRequest] = field(default_factory=list)
    reasoning_content: Optional[str] = None
    tools_used: List[str] = field(default_factory=list)
    iteration_count: int = 0

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Builds context with skills and history
    2. Calls the LLM
    3. Executes tool calls
    4. Returns final response

    Usage:
        agent = AgentLoop(
            provider=llm_provider,
            skills=["investment-strategy-skill"],
            identity="你是一个投资分析师...",
            max_iterations=10
        )

        # 单次分析
        response = await agent.run_once("分析铜行业投资机会")
        print(response.content)
    """

    def __init__(
        self,
        provider: Any,  # LLM provider (GeminiClient, DeepSeekClient, etc.)
        tools: Optional[List[BaseTool]] = None,
        skills: Optional[List[str]] = None,
        identity: str = "You are a helpful AI assistant.",
        max_iterations: int = 20,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        memory_window: int = 10,
        skills_dir: Optional[str] = None,
        additional_context: Optional[str] = None,
    ):
        """
        Initialize the agent loop.

        Args:
            provider: LLM provider instance (GeminiClient, etc.)
            tools: List of tools the agent can use
            skills: List of skill names to load
            identity: Core identity description
            max_iterations: Maximum tool call iterations
            temperature: LLM temperature
            max_tokens: Maximum tokens in response
            memory_window: Number of messages to keep in history
            skills_dir: Directory containing skills
            additional_context: Additional context to include in system prompt
        """
        self.provider = provider
        self.skills = skills or []
        self.identity = identity
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window

        # Initialize components
        self.context = AgentContextBuilder(skills_dir)
        self.tools = ToolRegistry()

        # Register tools
        if tools:
            for tool in tools:
                self.tools.register(tool)

        # Build system prompt
        self.system_prompt = self.context.build_system_prompt(
            identity=identity,
            skill_names=skills,
            additional_context=additional_context
        )

        # Message history
        self._history: List[Dict[str, Any]] = []

    @staticmethod
    def _strip_think(text: Optional[str]) -> Optional[str]:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    @staticmethod
    def _tool_hint(tool_calls: List[ToolCallRequest]) -> str:
        """Format tool calls as concise hint."""
        def _fmt(tc: ToolCallRequest) -> str:
            val = next(iter(tc.arguments.values()), None) if tc.arguments else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    async def _run_agent_loop(
        self,
        user_message: str,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> AgentResponse:
        """
        Run the agent iteration loop.

        Args:
            user_message: User's message
            on_progress: Callback for progress updates

        Returns:
            AgentResponse with final content and metadata
        """
        # Build initial messages
        messages = self.context.build_messages(
            system_prompt=self.system_prompt,
            history=self._history[-self.memory_window:],
            current_message=user_message
        )

        iteration = 0
        final_content = None
        tools_used: List[str] = []
        final_reasoning = None

        while iteration < self.max_iterations:
            iteration += 1

            # Call LLM
            response = await self._call_llm(messages)

            if response.has_tool_calls:
                # Report progress
                if on_progress:
                    clean = self._strip_think(response.content)
                    if clean:
                        on_progress(clean)
                    on_progress(self._tool_hint(response.tool_calls))

                # Add assistant message with tool calls
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages,
                    response.content,
                    tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )

                # Execute tools
                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                # Final response
                final_content = self._strip_think(response.content)
                final_reasoning = response.reasoning_content
                break

        # Handle max iterations reached
        if final_content is None and iteration >= self.max_iterations:
            final_content = (
                f"Reached maximum iterations ({self.max_iterations}) "
                "without completing the task."
            )

        # Update history
        self._update_history(user_message, final_content, tools_used)

        return AgentResponse(
            content=final_content,
            reasoning_content=final_reasoning,
            tools_used=tools_used,
            iteration_count=iteration
        )

    async def _call_llm(self, messages: List[Dict[str, Any]]) -> AgentResponse:
        """
        Call the LLM provider.

        Args:
            messages: List of messages

        Returns:
            AgentResponse
        """
        try:
            # Try different provider interfaces
            if hasattr(self.provider, 'chat'):
                # Nanobot-style provider
                response = await self.provider.chat(
                    messages=messages,
                    tools=self.tools.get_definitions(),
                    model=getattr(self.provider, 'model', None),
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )

                tool_calls = []
                if hasattr(response, 'tool_calls') and response.tool_calls:
                    tool_calls = [
                        ToolCallRequest(
                            id=tc.id,
                            name=tc.name,
                            arguments=tc.arguments
                        )
                        for tc in response.tool_calls
                    ]

                return AgentResponse(
                    content=response.content,
                    tool_calls=tool_calls,
                    reasoning_content=getattr(response, 'reasoning_content', None)
                )

            elif hasattr(self.provider, 'generate_content'):
                # Gemini-style provider
                from google.genai.types import GenerateContentConfig, ThinkingConfig

                config = GenerateContentConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                    thinking_config=ThinkingConfig(
                        mode="THINKING_MODE_ENABLED",
                        include_thoughts=False
                    )
                )

                # Convert messages to Gemini format
                prompt = self._messages_to_prompt(messages)

                response = await self.provider.aio.models.generate_content(
                    model=getattr(self.provider, 'model', 'gemini-2.0-flash-thinking-exp-01-21'),
                    contents=prompt,
                    config=config
                )

                return AgentResponse(
                    content=response.text,
                    tool_calls=[],  # Gemini doesn't support tool calls in this interface
                    reasoning_content=None
                )

            else:
                raise ValueError(f"Unsupported provider type: {type(self.provider)}")

        except Exception as e:
            print(f"[!] LLM call error: {e}")
            return AgentResponse(
                content=f"Error calling LLM: {str(e)}"
            )

    def _messages_to_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Convert messages to a single prompt string for Gemini."""
        parts = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            if role == 'system':
                parts.append(f"System: {content}")
            elif role == 'assistant':
                parts.append(f"Assistant: {content}")
            elif role == 'tool':
                parts.append(f"Tool Result: {content}")
            else:
                parts.append(f"User: {content}")

        return "\n\n".join(parts)

    def _update_history(
        self,
        user_message: str,
        assistant_content: Optional[str],
        tools_used: List[str]
    ):
        """Update conversation history."""
        self._history.append({"role": "user", "content": user_message})

        if assistant_content:
            self._history.append({
                "role": "assistant",
                "content": assistant_content,
                "tools_used": tools_used
            })

    async def run_once(
        self,
        message: str,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> AgentResponse:
        """
        Run the agent on a single message.

        Args:
            message: User message
            on_progress: Callback for progress updates

        Returns:
            AgentResponse
        """
        return await self._run_agent_loop(message, on_progress)

    def clear_history(self):
        """Clear conversation history."""
        self._history.clear()

    def get_history(self) -> List[Dict[str, Any]]:
        """Get conversation history."""
        return list(self._history)
