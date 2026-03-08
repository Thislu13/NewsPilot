"""Web tools for search and fetching."""

import aiohttp
from typing import Any

from .base import Tool


class WebSearchTool(Tool):
    """Tool for web search using Brave Search API."""

    def __init__(self, api_key: str | None = None):
        """
        Initialize WebSearchTool.

        Args:
            api_key: Brave Search API key
        """
        self.api_key = api_key

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web using Brave Search API"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of results (default: 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        }

    async def execute(self, query: str, count: int = 5) -> str:
        """Execute web search."""
        if not self.api_key:
            return "Error: Brave Search API key not configured"

        try:
            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
            }
            params = {"q": query, "count": count}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status != 200:
                        return f"Error: Search API returned status {response.status}"

                    data = await response.json()

                    # Format results
                    results = []
                    for i, result in enumerate(data.get("web", {}).get("results", []), 1):
                        title = result.get("title", "No title")
                        url = result.get("url", "")
                        description = result.get("description", "")
                        results.append(f"{i}. {title}\n   URL: {url}\n   {description}\n")

                    if not results:
                        return f"No results found for: {query}"

                    return "\n".join(results)

        except Exception as e:
            return f"Error performing web search: {str(e)}"


class WebFetchTool(Tool):
    """Tool for fetching web page content."""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "Fetch content from a URL"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch",
                    }
                },
                "required": ["url"],
            },
        }

    async def execute(self, url: str) -> str:
        """Fetch web page content."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        return f"Error: HTTP {response.status}"

                    content_type = response.headers.get("Content-Type", "")

                    if "text/html" in content_type or "text/plain" in content_type:
                        text = await response.text()
                        # Limit response size
                        if len(text) > 50000:
                            text = text[:50000] + "\n\n[Content truncated...]"
                        return text
                    else:
                        return f"Error: Unsupported content type: {content_type}"

        except asyncio.TimeoutError:
            return "Error: Request timed out"
        except Exception as e:
            return f"Error fetching URL: {str(e)}"
