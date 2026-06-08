from __future__ import annotations

from pathlib import Path

from app.agent.skills import SkillRegistry


def test_list_manifests_does_not_read_entire_skill_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    '''验证扫描 skill 元信息时不会通过 read_text 读取整个 SKILL.md。'''
    skill_dir = tmp_path / "skills" / "partial-read-skill"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "\n".join(
            [
                "---",
                "name: partial-read-skill",
                "description: test skill",
                "---",
                "",
                "# Body",
                "这一段正文不应该在扫描 manifest 时被整体读取。",
            ]
        ),
        encoding="utf-8",
    )

    original_read_text = Path.read_text

    def guarded_read_text(
        path: Path,
        *args,
        **kwargs,
    ) -> str:
        if path == skill_file:
            raise AssertionError("list_manifests 不应通过 read_text 读取整个 SKILL.md。")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    registry = SkillRegistry(
        skills_dir=tmp_path / "skills",
        workspace_root=tmp_path,
    )
    manifests = registry.list_manifests()

    assert len(manifests) == 1
    assert manifests[0].name == "partial-read-skill"
    assert manifests[0].description == "test skill"
