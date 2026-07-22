#!/usr/bin/env python3
"""Build deterministic Cowork plugin and project-template archives."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

from validate_plugin import validate


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "zed-seo-operator"
WORKSPACE_TEMPLATE = ROOT / "workspace-template"
DIST = ROOT / "dist"
PLUGIN_OUTPUT = DIST / "zed-seo-operator.plugin"
PROJECT_OUTPUT = DIST / "zed-seo-cowork-project.zip"
FIXED_TIMESTAMP = (2026, 7, 22, 0, 0, 0)


def archive_tree(source: Path, destination: Path, prefix: str = "") -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            relative = path.relative_to(source).as_posix()
            archive_name = f"{prefix.rstrip('/')}/{relative}" if prefix else relative
            info = zipfile.ZipInfo(archive_name, date_time=FIXED_TIMESTAMP)
            mode = 0o755 if path.suffix == ".py" else 0o644
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())


def main() -> int:
    errors = validate()
    if errors:
        print(json.dumps({"built": False, "errors": errors}, indent=2))
        return 1
    archive_tree(PLUGIN, PLUGIN_OUTPUT)
    archive_tree(WORKSPACE_TEMPLATE, PROJECT_OUTPUT, "Zed SEO Cowork Project")
    print(
        json.dumps(
            {
                "built": True,
                "plugin": str(PLUGIN_OUTPUT),
                "plugin_bytes": PLUGIN_OUTPUT.stat().st_size,
                "project_template": str(PROJECT_OUTPUT),
                "project_template_bytes": PROJECT_OUTPUT.stat().st_size,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
