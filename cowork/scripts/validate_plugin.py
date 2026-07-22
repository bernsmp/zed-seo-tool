#!/usr/bin/env python3
"""Validate the source form of the Zed SEO Cowork plugin."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "zed-seo-operator"
MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
EXPECTED_SKILLS = {
    "zed-seo-setup",
    "zed-seo-client",
    "zed-seo-research",
    "zed-seo-clean",
    "zed-seo-map",
    "zed-seo-resume",
    "zed-seo-report",
}
SECRET_PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    "provider secret": re.compile(r"sk-[0-9A-Za-z_-]{12,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def validate() -> list[str]:
    errors: list[str] = []
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return [f"Invalid plugin manifest: {exc}"]

    if manifest.get("name") != PLUGIN.name:
        errors.append("Plugin folder and manifest name must match.")
    for field in ("version", "description", "author"):
        if not manifest.get(field):
            errors.append(f"Manifest is missing '{field}'.")

    skill_names: set[str] = set()
    for skill_file in sorted((PLUGIN / "skills").glob("*/SKILL.md")):
        text = skill_file.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            errors.append(f"Skill lacks YAML frontmatter: {skill_file}")
            continue
        match = re.search(r"^name:\s*([^\n]+)$", text, flags=re.MULTILINE)
        if not match:
            errors.append(f"Skill has no name: {skill_file}")
            continue
        skill_name = match.group(1).strip()
        skill_names.add(skill_name)
        if skill_file.parent.name != skill_name:
            errors.append(f"Skill folder and name differ: {skill_file}")
        if "description:" not in text.split("---", 2)[1]:
            errors.append(f"Skill has no description: {skill_file}")

    if skill_names != EXPECTED_SKILLS:
        errors.append(
            "Skill set differs from the release contract. "
            f"Expected {sorted(EXPECTED_SKILLS)}, found {sorted(skill_names)}."
        )

    required = {
        PLUGIN / "README.md",
        PLUGIN / "scripts" / "jobctl.py",
        PLUGIN / "references" / "client-profile-schema.md",
        PLUGIN / "references" / "result-contracts.md",
        PLUGIN / "references" / "semrush-connector.md",
    }
    for path in required:
        if not path.is_file():
            errors.append(f"Missing required file: {path.relative_to(ROOT)}")

    total_size = 0
    for path in PLUGIN.rglob("*"):
        if path.is_symlink():
            errors.append(f"Symlinks are not allowed in the package: {path}")
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            errors.append(f"Generated Python artifact found: {path}")
            continue
        total_size += path.stat().st_size
        if path.suffix.lower() in {".md", ".json", ".py", ".txt"}:
            text = path.read_text(encoding="utf-8")
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    errors.append(f"Possible {label} in {path.relative_to(ROOT)}")

    if total_size > 200 * 1024 * 1024:
        errors.append("Plugin exceeds Cowork's 200 MB uncompressed limit.")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "valid": True,
                "plugin": str(PLUGIN),
                "skills": sorted(EXPECTED_SKILLS),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
