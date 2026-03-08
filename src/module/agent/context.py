#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-03-08 15:52:24
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-03-08 16:44:10
# FilePath: \NewsPilot\src\module\agent\context.py
# Description: 
# 
# Copyright (c) 2026 by , All Rights Reserved. 

"""Context builder for assembling agent prompts."""

import platform
from pathlib import Path

from .skills.loader import SkillsLoader


class SimpleContextBuilder:
    """
    Builds the context (system prompt) for the agent.

    Assembles skills and identity into a coherent prompt for the LLM.
    No memory management - designed for stateless single-call execution.
    """

    def __init__(self, workspace: Path):
        """
        Initialize SimpleContextBuilder.

        Args:
            workspace: Workspace directory
        """
        self.workspace = workspace
        self.skills = SkillsLoader(workspace)

    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """
        Build the system prompt.

        Args:
            skill_names: Optional list of skills to include

        Returns:
            Complete system prompt
        """
        parts = []

        # Core identity
        parts.append(self._get_identity())

        # Always-loaded skills
        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")

        # Available skills summary
        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(
                f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.

{skills_summary}"""
            )

        return "\n\n---\n\n".join(parts)

    def _get_identity(self) -> str:
        """Get the core identity section."""
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

        return f"""# Simple Agent 🤖
You are a helpful AI assistant for single-call execution.

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

## Tool Call Guidelines
- Before calling tools, you may briefly state your intent, but NEVER predict the result before receiving it.
- Before modifying a file, read it first to confirm its current content.
- Do not assume a file or directory exists — use list_dir or read_file to verify.
- After writing or editing a file, re-read it if accuracy matters.
- If a tool call fails, analyze the error before retrying with a different approach.
- You can spawn sub-agents using the 'spawn' tool to handle complex subtasks independently."""
