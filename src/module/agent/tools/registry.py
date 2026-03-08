"""Tool registry for managing and executing tools."""

from typing import Any

from .base import Tool


class ToolRegistry:
    """
    Registry for managing tools.

    Handles tool registration, lookup, and execution.
    """

    def __init__(self):
        """Initialize empty tool registry."""
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """
        Register a tool.

        Args:
            tool: Tool instance to register
        """
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def get_definitions(self) -> list[dict[str, Any]]:
        """
        Get all tool definitions in OpenAI format.

        Returns:
            List of tool definition dicts
        """
        return [
            {"type": "function", "function": tool.get_schema()}
            for tool in self._tools.values()
        ]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """
        Execute a tool by name.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        tool = self.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found"

        try:
            return await tool.execute(**arguments)
        except Exception as e:
            return f"Error executing {name}: {str(e)}"
