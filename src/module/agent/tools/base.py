"""Tool base classes and interfaces."""

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """
    Abstract base class for tools.

    Tools extend the agent's capabilities by providing
    specific functionality like file operations, web search, etc.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name (used in function calls)."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for the LLM."""
        pass

    @abstractmethod
    def get_schema(self) -> dict[str, Any]:
        """
        Get the tool's JSON Schema definition.

        Returns:
            OpenAI function calling format schema with name, description, and parameters
        """
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """
        Execute the tool with given arguments.

        Args:
            **kwargs: Tool-specific arguments

        Returns:
            Tool execution result as string
        """
        pass
