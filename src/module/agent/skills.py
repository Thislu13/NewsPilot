"""
Skills loader for agent capabilities.
从 nanobot 移植并适配到 NewsPilot
"""

import re
from pathlib import Path
from typing import Dict, List, Optional


class SkillsLoader:
    """
    Loader for agent skills.

    Skills are markdown files (skill.md) that teach the agent how to use
    specific tools or perform certain tasks.
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        """
        Initialize the skills loader.

        Args:
            skills_dir: Directory containing skills. Defaults to project_root/skills.
        """
        if skills_dir is None:
            # Default to project root skills directory
            project_root = Path(__file__).parent.parent.parent
            skills_dir = project_root / "skills"

        self.skills_dir = Path(skills_dir)
        self._cache: Dict[str, str] = {}

    def list_skills(self) -> List[Dict[str, str]]:
        """
        List all available skills.

        Returns:
            List of skill info dicts with 'name', 'path'.
        """
        skills = []

        if not self.skills_dir.exists():
            return skills

        for skill_dir in self.skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "skill.md"
                if skill_file.exists():
                    skills.append({
                        "name": skill_dir.name,
                        "path": str(skill_file)
                    })

        return skills

    def load_skill(self, name: str) -> Optional[str]:
        """
        Load a skill by name.

        Args:
            name: Skill name (directory name).

        Returns:
            Skill content or None if not found.
        """
        # Check cache
        if name in self._cache:
            return self._cache[name]

        skill_file = self.skills_dir / name / "skill.md"
        if not skill_file.exists():
            return None

        content = skill_file.read_text(encoding="utf-8")
        self._cache[name] = content
        return content

    def load_skills_for_context(self, skill_names: List[str]) -> str:
        """
        Load specific skills for inclusion in agent context.

        Args:
            skill_names: List of skill names to load.

        Returns:
            Formatted skills content.
        """
        parts = []
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                content = self._strip_frontmatter(content)
                parts.append(f"### Skill: {name}\n\n{content}")

        return "\n\n---\n\n".join(parts) if parts else ""

    def build_skills_summary(self) -> str:
        """
        Build a summary of all skills.

        Returns:
            Formatted skills summary.
        """
        all_skills = self.list_skills()
        if not all_skills:
            return ""

        lines = ["## Available Skills", ""]
        for s in all_skills:
            name = s["name"]
            desc = self._get_skill_description(name)
            lines.append(f"- **{name}**: {desc}")

        return "\n".join(lines)

    def _get_skill_description(self, name: str) -> str:
        """Get the description of a skill from its frontmatter."""
        meta = self._get_skill_metadata(name)
        if meta and meta.get("description"):
            return meta["description"]

        # Fallback: extract first heading
        content = self.load_skill(name)
        if content:
            match = re.search(r"^#+\s+(.+)$", content, re.MULTILINE)
            if match:
                return match.group(1)

        return name

    def _strip_frontmatter(self, content: str) -> str:
        """Remove YAML frontmatter from markdown content."""
        if content.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end():].strip()
        return content

    def _get_skill_metadata(self, name: str) -> Optional[Dict[str, str]]:
        """
        Get metadata from a skill's frontmatter.

        Args:
            name: Skill name.

        Returns:
            Metadata dict or None.
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
