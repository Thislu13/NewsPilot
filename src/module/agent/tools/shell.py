"""Shell execution tool."""

import asyncio
import os
from pathlib import Path
from typing import Any

from .base import Tool


class ExecTool(Tool):
    """Tool for executing shell commands."""

    def __init__(
        self,
        working_dir: str,
        timeout: int = 120,
        restrict_to_workspace: bool = False,
    ):
        """
        Initialize ExecTool.

        Args:
            working_dir: Working directory for commands
            timeout: Command timeout in seconds
            restrict_to_workspace: Restrict commands to workspace
        """
        self.working_dir = working_dir
        self.timeout = timeout
        self.restrict_to_workspace = restrict_to_workspace

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return "Execute a shell command and return its output"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    }
                },
                "required": ["command"],
            },
        }

    async def execute(self, command: str) -> str:
        """Execute shell command."""
        try:
            # Security check for dangerous commands
            dangerous_patterns = ["rm -rf /", ":(){ :|:& };:", "mkfs", "dd if="]
            if any(pattern in command for pattern in dangerous_patterns):
                return f"Error: Dangerous command blocked: {command}"

            # Execute command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return f"Error: Command timed out after {self.timeout} seconds"

            # Format output
            output_parts = []
            if stdout:
                output_parts.append(f"STDOUT:\n{stdout.decode('utf-8', errors='replace')}")
            if stderr:
                output_parts.append(f"STDERR:\n{stderr.decode('utf-8', errors='replace')}")

            if not output_parts:
                return f"Command completed with no output (exit code: {process.returncode})"

            result = "\n\n".join(output_parts)
            result += f"\n\nExit code: {process.returncode}"

            return result

        except Exception as e:
            return f"Error executing command: {str(e)}"
