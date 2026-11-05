"""Create a reviewable source diff and content manifest without touching the user's Git index."""
import difflib
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {".git", ".venv", ".tools", "node_modules", "dist", "artifacts", "__pycache__",
           ".pytest_cache", ".hypothesis", ".ruff_cache", "backups"}


def main():
    manifest = []
    patches = []
    for directory, subdirs, names in os.walk(ROOT):
        subdirs[:] = sorted(name for name in subdirs if name not in EXCLUDE)
        for name in sorted(names):
            path = Path(directory) / name
            relative = path.relative_to(ROOT).as_posix()
            if name.startswith(".env") and name != ".env.example":
                continue
            raw = path.read_bytes()
            text = raw.decode("utf-8-sig")
            manifest.append({"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            patches.extend(difflib.unified_diff([], text.splitlines(keepends=True),
                                                fromfile="/dev/null", tofile=f"b/{relative}"))
    (ROOT / "artifacts/implementation.patch").write_text("".join(patches), encoding="utf-8")
    (ROOT / "artifacts/source-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Reviewable diff + SHA-256 manifest: {len(manifest)} source/config/doc files")


if __name__ == "__main__":
    main()
