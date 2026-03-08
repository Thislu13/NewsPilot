"""Sub-agent spawning tool."""

from typing import Any, Callable, Awaitable

from .base import Tool


class SpawnTool(Tool):
    """
    Tool for spawning sub-agents to handle subtasks.

    Allows the main agent to delegate work to child agents.
    """

    def __init__(self, agent_factory: Callable[[int], Awaitable[Any]]):
        """
        Initialize SpawnTool.

        Args:
            agent_factory: Factory function to create sub-agents
        """
        self.agent_factory = agent_factory

    @property
    def name(self) -> str:
        return "spawn"

    @property
    def description(self) -> str:
        return "Spawn a sub-agent to handle a subtask independently"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Description of the subtask for the sub-agent",
                    },
                    "max_iterations": {
                        "type": "integer",
                        "description": "Maximum iterations for the sub-agent (default: 20)",
                        "default": 20,
                    },
                    "skill_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of skill names to load for the sub-agent (e.g., ['value-investment-strategy'])",
                        "default": None,
                    },
                },
                "required": ["task"],
            },
        }

    async def execute(self, task: str, max_iterations: int = 20, skill_names: list[str] | None = None) -> str:
        """
        Spawn a sub-agent to execute a task.

        Args:
            task: Task description
            max_iterations: Max iterations for sub-agent
            skill_names: Optional list of skill names to load for the sub-agent

        Returns:
            Sub-agent's result
        """
        try:
            # Create sub-agent
            sub_agent = await self.agent_factory(max_iterations)

            # Execute task with skills
            result = await sub_agent.ask(task, skill_names=skill_names)

            # Cleanup
            await sub_agent.close()

            return f"Sub-agent result:\n{result}"

        except Exception as e:
            return f"Error spawning sub-agent: {str(e)}"
