"""LiteLLM provider implementation."""

import json
import os
from typing import Any

import litellm
from litellm import acompletion

from .base import LLMProvider, LLMResponse, ToolCallRequest


class LiteLLMProvider(LLMProvider):
    """
    LLM provider using LiteLLM for multi-provider support.

    Supports OpenAI, Anthropic, Gemini, and many other providers
    through a unified interface.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "gpt-4",
    ):
        """
        Initialize LiteLLM provider.

        Args:
            api_key: API key for the provider
            api_base: Optional custom API base URL
            default_model: Default model to use
        """
        self.api_key = api_key
        self.api_base = api_base
        self.default_model = default_model

        # Configure LiteLLM
        if api_key:
            self._setup_env(api_key, default_model)

        if api_base:
            litellm.api_base = api_base

        # Disable LiteLLM logging noise
        litellm.suppress_debug_info = True
        # Drop unsupported parameters for providers
        litellm.drop_params = True

    def _setup_env(self, api_key: str, model: str) -> None:
        """Set environment variables based on model."""
        model_lower = model.lower()

        # Set appropriate env var based on model prefix
        if "gemini" in model_lower:
            os.environ.setdefault("GEMINI_API_KEY", api_key)
        elif "claude" in model_lower or "anthropic" in model_lower:
            os.environ.setdefault("ANTHROPIC_API_KEY", api_key)
        elif "gpt" in model_lower or "openai" in model_lower:
            os.environ.setdefault("OPENAI_API_KEY", api_key)
        else:
            # Default to OpenAI
            os.environ.setdefault("OPENAI_API_KEY", api_key)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Send a chat completion request via LiteLLM.

        Args:
            messages: List of message dicts
            tools: Optional tool definitions
            model: Model identifier
            max_tokens: Maximum tokens
            temperature: Sampling temperature

        Returns:
            LLMResponse with content and/or tool calls
        """
        model = model or self.default_model

        # Clamp max_tokens to at least 1
        max_tokens = max(1, max_tokens)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._sanitize_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # Pass api_key directly
        if self.api_key:
            kwargs["api_key"] = self.api_key

        # Pass api_base for custom endpoints
        if self.api_base:
            kwargs["api_base"] = self.api_base

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await acompletion(**kwargs)
            return self._parse_response(response)
        except Exception as e:
            # Return error as content for graceful handling
            return LLMResponse(
                content=f"Error calling LLM: {str(e)}",
                finish_reason="error",
            )

    def _sanitize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sanitize messages for LiteLLM."""
        sanitized = []
        for msg in messages:
            # Keep only standard keys
            clean = {
                k: v
                for k, v in msg.items()
                if k in {"role", "content", "tool_calls", "tool_call_id", "name"}
            }
            # Ensure assistant messages have content key
            if clean.get("role") == "assistant" and "content" not in clean:
                clean["content"] = None
            sanitized.append(clean)
        return sanitized

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse LiteLLM response into our standard format."""
        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                # Parse arguments from JSON string if needed
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                tool_calls.append(
                    ToolCallRequest(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args,
                    )
                )

        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
        )

    def get_default_model(self) -> str:
        """Get the default model."""
        return self.default_model
