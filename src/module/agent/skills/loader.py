"""Skills loader for agent capabilities."""

import re
from pathlib import Path


class SkillsLoader:
    """
    Loader for agent skills.

    Skills are markdown files (SKILL.md) that teach the agent
    how to use specific tools or perform certain tasks.
    """

    def __init__(self, workspace: Path):
        """
        Initialize SkillsLoader.

        Args:
            workspace: Workspace directory
        """
        self.workspace = workspace
        self.workspace_skills = workspace / "skills"
        # Also check for built-in skills in the framework
        self.builtin_skills = Path(__file__).parent

    def list_skills(self) -> list[dict[str, str]]:
        """
        List all available skills.

        Returns:
            List of skill info dicts with 'name' and 'path'
        """
        skills = []

        # Load from workspace skills
        if self.workspace_skills.exists():
            for skill_dir in self.workspace_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skills.append({
                            "name": skill_dir.name,
                            "path": str(skill_file),
                            "source": "workspace",
                        })

        # Load from built-in skills (framework)
        if self.builtin_skills.exists():
            for skill_dir in self.builtin_skills.iterdir():
                if skill_dir.is_dir() and skill_dir.name != "__pycache__":
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        # Avoid duplicates (workspace takes priority)
                        if not any(s["name"] == skill_dir.name for s in skills):
                            skills.append({
                                "name": skill_dir.name,
                                "path": str(skill_file),
                                "source": "builtin",
                            })

        return skills

    def load_skill(self, name: str) -> str | None:
        """
        Load a skill by name.

        Args:
            name: Skill name (directory name)

        Returns:
            Skill content or None if not found
        """
        # Check workspace first (higher priority)
        workspace_skill = self.workspace_skills / name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill.read_text(encoding="utf-8")

        # Check built-in skills
        builtin_skill = self.builtin_skills / name / "SKILL.md"
        if builtin_skill.exists():
            return builtin_skill.read_text(encoding="utf-8")

        return None

    def get_always_skills(self) -> list[str]:
        """
        Get skills marked as always=true.

        Returns:
            List of skill names
        """
        always_skills = []

        for skill in self.list_skills():
            metadata = self.get_skill_metadata(skill["name"])
            if metadata and metadata.get("always") == "true":
                always_skills.append(skill["name"])

        return always_skills

    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """
        Load specific skills for inclusion in agent context.

        Args:
            skill_names: List of skill names to load

        Returns:
            Formatted skills content
        """
        parts = []

        for name in skill_names:
            content = self.load_skill(name)
            if content:
                # Strip frontmatter
                content = self._strip_frontmatter(content)
                parts.append(f"### Skill: {name}\n\n{content}")

        return "\n\n---\n\n".join(parts) if parts else ""

    def build_skills_summary(self) -> str:
        """
        Build a summary of all skills.

        Returns:
            XML-formatted skills summary
        """
        all_skills = self.list_skills()
        if not all_skills:
            return ""

        lines = ["<skills>"]
        for skill in all_skills:
            name = skill["name"]
            path = skill["path"]
            desc = self._get_skill_description(name)

            lines.append(f'  <skill>')
            lines.append(f'    <name>{name}</name>')
            lines.append(f'    <description>{desc}</description>')
            lines.append(f'    <location>{path}</location>')
            lines.append(f'  </skill>')

        lines.append("</skills>")

        return "\n".join(lines)

    def _get_skill_description(self, name: str) -> str:
        """Get the description of a skill from its frontmatter."""
        metadata = self.get_skill_metadata(name)
        if metadata and metadata.get("description"):
            return metadata["description"]
        return name

    def _strip_frontmatter(self, content: str) -> str:
        """Remove YAML frontmatter from markdown content."""
        if content.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end():].strip()
        return content

    def get_skill_metadata(self, name: str) -> dict[str, str] | None:
        """
        Get metadata from a skill's frontmatter.

        Args:
            name: Skill name

        Returns:
            Metadata dict or None
        """
        content = self.load_skill(name)
        if not content:
            return None

        if content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                # Simple YAML parsing
                metadata = {}
                for line in match.group(1).split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        metadata[key.strip()] = value.strip().strip('"\'')
                return metadata

        return None
