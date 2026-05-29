from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(".").resolve()
OUTPUT = ROOT / "repo-index.json"

REPO = os.environ.get("GITHUB_REPOSITORY", "")
BRANCH = os.environ.get("GITHUB_REF_NAME", "")

EXCLUDED_FILES = {
    "repo-index.json",
}
EXCLUDED_DIRS = {
    ".git",
}


def iter_repo_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue

        rel = path.relative_to(root)

        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue

        if rel.name in EXCLUDED_FILES:
            continue

        yield rel


def classify_file(rel: Path) -> str:
    parts = rel.parts
    name = rel.name.lower()
    suffix = rel.suffix.lower()

    if parts and parts[0] == ".github":
        return "repo_meta"
    if parts and parts[0].lower() == "tests":
        return "test"
    if parts and parts[0].lower() in {"docs", "doc"}:
        return "documentation"
    if suffix in {".md", ".rst", ".txt"}:
        return "documentation"
    if "test" in name:
        return "test"
    return "code_or_asset"


def build_raw_url(rel: Path) -> str:
    encoded = quote(rel.as_posix(), safe="/")
    return f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{encoded}"


def build_github_url(rel: Path) -> str:
    encoded = quote(rel.as_posix(), safe="/")
    return f"https://github.com/{REPO}/blob/{BRANCH}/{encoded}"


def main() -> None:
    files = []

    for rel in sorted(iter_repo_files(ROOT), key=lambda p: p.as_posix().lower()):
        full = ROOT / rel
        stat = full.stat()

        files.append(
            {
                "path": rel.as_posix(),
                "filename": rel.name,
                "extension": rel.suffix.lower().lstrip("."),
                "size_bytes": stat.st_size,
                "top_level_dir": rel.parts[0] if rel.parts else "",
                "category": classify_file(rel),
                "raw_url": build_raw_url(rel),
                "github_url": build_github_url(rel),
            }
        )

    payload = {
        "repo": REPO,
        "branch": BRANCH,
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "file_count": len(files),
        "files": files,
    }

    # Clear the file before writing new data
    OUTPUT.write_text("", encoding="utf-8")

    # Write the new data
    OUTPUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()