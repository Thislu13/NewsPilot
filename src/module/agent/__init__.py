"""Simple Agent - Independent single-call agent framework."""

from .context import SimpleContextBuilder
from .providers import LiteLLMProvider, LLMProvider, LLMResponse, ToolCallRequest
from .simple_agent import SimpleAgent
from .skills import SkillsLoader
from .tools import (
    EditFileTool,
    ExecTool,
    ListDirTool,
    ReadFileTool,
    SpawnTool,
    Tool,
    ToolRegistry,
    WebFetchTool,
    WebSearchTool,
    WriteFileTool,
)

__version__ = "1.0.0"

__all__ = [
    # Main agent
    "SimpleAgent",
    # Providers
    "LLMProvider",
    "LLMResponse",
    "ToolCallRequest",
    "LiteLLMProvider",
    # Tools
    "Tool",
    "ToolRegistry",
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "ListDirTool",
    "ExecTool",
    "WebSearchTool",
    "WebFetchTool",
    "SpawnTool",
    # Skills
    "SkillsLoader",
    # Context
    "SimpleContextBuilder",
]
