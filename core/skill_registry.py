from __future__ import annotations
import importlib
import json
import sys
from pathlib import Path
from typing import Any
from config import ROOT_DIR, SKILLS_DIR
from core.skill import BaseSkill


class SkillRegistry:
    _skills: dict[str, BaseSkill] = {}
    _errors: list[str] = []

    @classmethod
    def discover_skills(cls, force: bool = False) -> dict[str, BaseSkill]:
        if cls._skills and not force:
            return cls._skills
        cls._skills.clear()
        cls._errors.clear()
        root = str(ROOT_DIR)
        if root not in sys.path:
            sys.path.insert(0, root)
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        for folder in sorted(SKILLS_DIR.iterdir()):
            manifest_path = folder / "manifest.json"
            module_path = folder / "skill.py"
            if not folder.is_dir() or not manifest_path.is_file() or not module_path.is_file():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("enabled", True) is False:
                    continue
                module = importlib.import_module(f"skills.{folder.name}.skill")
                importlib.reload(module)
                candidates = [
                    getattr(module, name) for name in dir(module)
                    if isinstance(getattr(module, name), type)
                    and issubclass(getattr(module, name), BaseSkill)
                    and getattr(module, name) is not BaseSkill
                    and getattr(module, name).__module__ == module.__name__
                ]
                if len(candidates) != 1:
                    raise ValueError(f"Cần đúng 1 class BaseSkill trong {folder.name}, tìm thấy {len(candidates)}")
                instance = candidates[0]()
                declared_name = manifest.get("name")
                if declared_name and declared_name != instance.manifest.name:
                    raise ValueError(f"Tên manifest '{declared_name}' không khớp skill '{instance.manifest.name}'")
                if instance.manifest.name in cls._skills:
                    raise ValueError(f"Trùng tên skill: {instance.manifest.name}")
                cls._skills[instance.manifest.name] = instance
            except Exception as exc:
                cls._errors.append(f"{folder.name}: {exc}")
        return cls._skills

    @classmethod
    def get_skill(cls, name: str) -> BaseSkill | None:
        return cls._skills.get(name)

    @classmethod
    def get_manifests(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": skill.manifest.name,
                "version": skill.manifest.version,
                "description": skill.manifest.description,
                "input_schema": skill.manifest.input_schema,
                "permissions": skill.manifest.permissions,
            }
            for skill in cls._skills.values()
        ]

    @classmethod
    def get_manifest_context(cls) -> str:
        return json.dumps(cls.get_manifests(), ensure_ascii=False, indent=2)

    @classmethod
    def get_errors(cls) -> list[str]:
        return list(cls._errors)
