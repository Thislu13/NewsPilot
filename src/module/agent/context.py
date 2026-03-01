"""
Context builder for assembling agent prompts.
从 nanobot 移植并适配到 NewsPilot
"""

import base64
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .skills import SkillsLoader


class AgentContextBuilder:
    """
    Builds the context (system prompt + messages) for the agent.

    Assembles skills and conversation history into a coherent prompt for the LLM.
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        """
        Initialize the context builder.

        Args:
            skills_dir: Directory containing skills.
        """
        self.skills = SkillsLoader(skills_dir)

    def build_system_prompt(
        self,
        identity: str,
        skill_names: Optional[List[str]] = None,
        additional_context: Optional[str] = None
    ) -> str:
        """
        Build the system prompt from identity, skills, and additional context.

        Args:
            identity: Core identity description for the agent.
            skill_names: Optional list of skills to include.
            additional_context: Optional additional context to include.

        Returns:
            Complete system prompt.
        """
        parts = []

        # Core identity
        parts.append(f"# Identity\n\n{identity}")

        # Skills
        if skill_names:
            skills_content = self.skills.load_skills_for_context(skill_names)
            if skills_content:
                parts.append(f"# Skills\n\n{skills_content}")

        # Available skills summary
        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(skills_summary)

        # Additional context
        if additional_context:
            parts.append(f"# Additional Context\n\n{additional_context}")

        return "\n\n---\n\n".join(parts)

    def build_messages(
        self,
        system_prompt: str,
        history: List[Dict[str, Any]],
        current_message: str,
        media: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Build the complete message list for an LLM call.

        Args:
            system_prompt: The system prompt.
            history: Previous conversation messages.
            current_message: The new user message.
            media: Optional list of local file paths for images/media.

        Returns:
            List of messages including system prompt.
        """
        messages = []

        # System prompt
        messages.append({"role": "system", "content": system_prompt})

        # History
        messages.extend(history)

        # Current message (with optional image attachments)
        user_content = self._build_user_content(current_message, media)
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_content(
        self,
        text: str,
        media: Optional[List[str]] = None
    ) -> Union[str, List[Dict[str, Any]]]:
        """Build user message content with optional base64-encoded images."""
        if not media:
            return text

        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"}
            })

        if not images:
            return text

        return images + [{"type": "text", "text": text}]

    def add_tool_result(
        self,
        messages: List[Dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str
    ) -> List[Dict[str, Any]]:
        """
        Add a tool result to the message list.

        Args:
            messages: Current message list.
            tool_call_id: ID of the tool call.
            tool_name: Name of the tool.
            result: Tool execution result.

        Returns:
            Updated message list.
        """
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result
        })
        return messages

    def add_assistant_message(
        self,
        messages: List[Dict[str, Any]],
        content: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        reasoning_content: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Add an assistant message to the message list.

        Args:
            messages: Current message list.
            content: Message content.
            tool_calls: Optional tool calls.
            reasoning_content: Thinking output (Kimi, DeepSeek-R1, etc.).

        Returns:
            Updated message list.
        """
        msg: Dict[str, Any] = {"role": "assistant"}

        # Always include content
        msg["content"] = content

        if tool_calls:
            msg["tool_calls"] = tool_calls

        # Include reasoning content when provided
        if reasoning_content is not None:
            msg["reasoning_content"] = reasoning_content

        messages.append(msg)
        return messages

    def _get_runtime_context(self) -> str:
        """Get dynamic runtime context."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        return f"[Runtime Context]\nCurrent Time: {now}"

    def inject_runtime_context(self, message: str) -> str:
        """Inject runtime context into user message."""
        runtime = self._get_runtime_context()
        return f"{message}\n\n{runtime}"
