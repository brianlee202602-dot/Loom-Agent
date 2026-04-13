from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


@dataclass(frozen=True)
class SkillManifest:
    '''表示 skill 的轻量元数据，只用于路由阶段。'''

    name: str
    description: str
    compatibility: str | None
    metadata: dict[str, Any]
    root_dir: Path
    skill_file: Path

    @property
    def summary(self) -> dict[str, Any]:
        '''返回可直接提供给路由模型的 skill 摘要。'''
        return {
            "name": self.name,
            "description": self.description,
            "compatibility": self.compatibility,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class SkillDefinition(SkillManifest):
    '''表示已经展开后的完整 skill 定义。'''

    content: str
    available_files: tuple[str, ...]


class SkillRegistry:
    def __init__(self, *, skills_dir: Path, workspace_root: Path) -> None:
        '''初始化 skill 注册表，并准备缓存目录扫描结果。'''
        self.skills_dir = skills_dir
        self.workspace_root = workspace_root
        self._manifest_cache: dict[str, SkillManifest] = {}
        self._definition_cache: dict[str, SkillDefinition] = {}

    def list_manifests(self) -> list[SkillManifest]:
        '''返回所有已发现的 skill 摘要信息。'''
        if not self._manifest_cache:
            self._discover()
        return sorted(self._manifest_cache.values(), key=lambda item: item.name)

    def get_manifest(self, skill_name: str) -> SkillManifest:
        '''按名称获取单个 skill 的摘要信息。'''
        if not self._manifest_cache:
            self._discover()
        return self._manifest_cache[skill_name]

    def load_definition(self, skill_name: str) -> SkillDefinition:
        '''按需加载完整 skill 内容，实现渐进式披露。'''
        if skill_name in self._definition_cache:
            return self._definition_cache[skill_name]

        manifest = self.get_manifest(skill_name)
        content = manifest.skill_file.read_text(encoding="utf-8-sig")
        linked_files = [
            path
            for path in MARKDOWN_LINK_PATTERN.findall(content)
            if not path.startswith(("http://", "https://"))
        ]
        available_files = sorted(
            {
                "SKILL.md",
                *linked_files,
                *self._list_relative_files(manifest.root_dir / "references"),
                *self._list_relative_files(manifest.root_dir / "scripts"),
            }
        )

        definition = SkillDefinition(
            name=manifest.name,
            description=manifest.description,
            compatibility=manifest.compatibility,
            metadata=manifest.metadata,
            root_dir=manifest.root_dir,
            skill_file=manifest.skill_file,
            content=content,
            available_files=tuple(available_files),
        )
        self._definition_cache[skill_name] = definition
        return definition

    def _discover(self) -> None:
        '''扫描 skills 目录并建立 skill 摘要缓存。'''
        self._manifest_cache = {}
        if not self.skills_dir.exists():
            return

        for skill_file in sorted(self.skills_dir.glob("*/SKILL.md")):
            manifest = self._load_manifest(skill_file)
            self._manifest_cache[manifest.name] = manifest

    def _load_manifest(self, skill_file: Path) -> SkillManifest:
        '''从单个 SKILL.md 中提取 front matter 元信息。'''
        front_matter_text = self._read_front_matter(skill_file)
        parsed_front_matter = (
            yaml.safe_load(front_matter_text) if front_matter_text else {}
        )
        if not isinstance(parsed_front_matter, dict):
            parsed_front_matter = {}

        name = str(parsed_front_matter.get("name") or skill_file.parent.name)
        description = str(parsed_front_matter.get("description") or "").strip()
        compatibility = parsed_front_matter.get("compatibility")
        if compatibility is not None:
            compatibility = str(compatibility).strip()

        metadata = parsed_front_matter.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        return SkillManifest(
            name=name,
            description=description,
            compatibility=compatibility,
            metadata=metadata,
            root_dir=skill_file.parent,
            skill_file=skill_file,
        )

    def _read_front_matter(self, skill_file: Path) -> str:
        '''仅流式读取 SKILL.md 的 front matter，避免加载整个文件。'''
        with skill_file.open("r", encoding="utf-8-sig") as handle:
            first_line = handle.readline()
            if first_line.strip() != "---":
                return ""

            front_matter_lines: list[str] = []
            for line in handle:
                if line.strip() == "---":
                    return "".join(front_matter_lines)
                front_matter_lines.append(line)

        return ""

    def _list_relative_files(self, directory: Path) -> list[str]:
        '''列出指定目录下所有文件的相对路径。'''
        if not directory.exists():
            return []
        return [
            file_path.relative_to(directory.parent).as_posix()
            for file_path in sorted(path for path in directory.rglob("*") if path.is_file())
        ]
