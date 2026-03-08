"""Filesystem tools for file operations."""

import os
from pathlib import Path
from typing import Any

from .base import Tool


class ReadFileTool(Tool):
    """Tool for reading file contents."""

    def __init__(self, workspace: Path, allowed_dir: Path | None = None):
        """
        Initialize ReadFileTool.

        Args:
            workspace: Workspace directory
            allowed_dir: Optional directory restriction
        """
        self.workspace = workspace
        self.allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to read",
                    }
                },
                "required": ["file_path"],
            },
        }

    async def execute(self, file_path: str) -> str:
        """Read file contents."""
        try:
            path = Path(file_path)

            # Security check
            if self.allowed_dir:
                resolved = path.resolve()
                allowed = self.allowed_dir.resolve()
                if not str(resolved).startswith(str(allowed)):
                    return f"Error: Access denied - path outside allowed directory"

            if not path.exists():
                return f"Error: File not found: {file_path}"

            if not path.is_file():
                return f"Error: Not a file: {file_path}"

            content = path.read_text(encoding="utf-8")
            return content

        except Exception as e:
            return f"Error reading file: {str(e)}"


class WriteFileTool(Tool):
    """Tool for writing file contents."""

    def __init__(self, workspace: Path, allowed_dir: Path | None = None):
        self.workspace = workspace
        self.allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file (creates or overwrites)"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file",
                    },
                },
                "required": ["file_path", "content"],
            },
        }

    async def execute(self, file_path: str, content: str) -> str:
        """Write content to file."""
        try:
            path = Path(file_path)

            # Security check
            if self.allowed_dir:
                resolved = path.resolve()
                allowed = self.allowed_dir.resolve()
                if not str(resolved).startswith(str(allowed)):
                    return f"Error: Access denied - path outside allowed directory"

            # Create parent directories if needed
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            path.write_text(content, encoding="utf-8")

            return f"Successfully wrote {len(content)} characters to {file_path}"

        except Exception as e:
            return f"Error writing file: {str(e)}"


class EditFileTool(Tool):
    """Tool for editing file contents with find/replace."""

    def __init__(self, workspace: Path, allowed_dir: Path | None = None):
        self.workspace = workspace
        self.allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return "Edit a file by replacing old_text with new_text"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to edit",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "Text to find and replace",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "Text to replace with",
                    },
                },
                "required": ["file_path", "old_text", "new_text"],
            },
        }

    async def execute(self, file_path: str, old_text: str, new_text: str) -> str:
        """Edit file with find/replace."""
        try:
            path = Path(file_path)

            # Security check
            if self.allowed_dir:
                resolved = path.resolve()
                allowed = self.allowed_dir.resolve()
                if not str(resolved).startswith(str(allowed)):
                    return f"Error: Access denied - path outside allowed directory"

            if not path.exists():
                return f"Error: File not found: {file_path}"

            # Read current content
            content = path.read_text(encoding="utf-8")

            # Check if old_text exists
            if old_text not in content:
                return f"Error: Text not found in file: {old_text[:50]}..."

            # Replace
            new_content = content.replace(old_text, new_text)

            # Write back
            path.write_text(new_content, encoding="utf-8")

            return f"Successfully replaced text in {file_path}"

        except Exception as e:
            return f"Error editing file: {str(e)}"


class ListDirTool(Tool):
    """Tool for listing directory contents."""

    def __init__(self, workspace: Path, allowed_dir: Path | None = None):
        self.workspace = workspace
        self.allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "List contents of a directory"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "dir_path": {
                        "type": "string",
                        "description": "Path to the directory to list (default: current directory)",
                    }
                },
                "required": [],
            },
        }

    async def execute(self, dir_path: str = ".") -> str:
        """List directory contents."""
        try:
            path = Path(dir_path)

            # Security check
            if self.allowed_dir:
                resolved = path.resolve()
                allowed = self.allowed_dir.resolve()
                if not str(resolved).startswith(str(allowed)):
                    return f"Error: Access denied - path outside allowed directory"

            if not path.exists():
                return f"Error: Directory not found: {dir_path}"

            if not path.is_dir():
                return f"Error: Not a directory: {dir_path}"

            # List contents
            items = []
            for item in sorted(path.iterdir()):
                item_type = "DIR" if item.is_dir() else "FILE"
                size = item.stat().st_size if item.is_file() else 0
                items.append(f"{item_type:4} {size:>10} {item.name}")

            if not items:
                return f"Directory is empty: {dir_path}"

            return "\n".join(items)

        except Exception as e:
            return f"Error listing directory: {str(e)}"
