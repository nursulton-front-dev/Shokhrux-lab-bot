"""Create a reviewable patch and fixed-source archive without staging any files.

The patch targets historical Git commit 4edd46d, not an inferred task-start
snapshot. That snapshot contained additional pre-existing uncommitted features.
The patch therefore includes those features in the audited modules as well.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BASE = "4edd46d"
ROOT_FILES = [".dockerignore", ".env.example", ".gitignore", "DEPLOY.md", "Dockerfile", "docker-compose.yml",
              "fitness_bot.service", "requirements.txt", "requirements-dev.txt", "main.py", "run_polling.py",
              "run_migration.py", "rotate_invites.py", "self_test.py"]


def main() -> None:
    files = [ROOT / name for name in ROOT_FILES]
    files += sorted((ROOT / "bot").rglob("*.py"))
    files += sorted((ROOT / "tests").glob("*.py"))
    relative = [p.relative_to(ROOT).as_posix() for p in files if p.is_file()]
    patch = subprocess.check_output(["git", "diff", "--binary", BASE, "--", *relative], cwd=ROOT)
    tracked = set(subprocess.check_output(["git", "ls-files", "--", *relative], cwd=ROOT).decode().splitlines())
    for name in relative:
        if name in tracked:
            continue
        content = (ROOT / name).read_text().splitlines(keepends=True)
        patch += (f"diff --git a/{name} b/{name}\nnew file mode 100644\n" + "".join(
            difflib.unified_diff([], content, fromfile="/dev/null", tofile=f"b/{name}")
        )).encode()
    (ROOT / "audit/fixes.patch").write_bytes(patch)
    manifest = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in relative}
    (ROOT / "audit/fixed-files.json").write_text(json.dumps({"patch_base": BASE, "sha256": manifest}, indent=2) + "\n")
    with tarfile.open(ROOT / "audit/fixed-source.tar.gz", "w:gz") as archive:
        for name in relative:
            archive.add(ROOT / name, arcname=name, recursive=False)
    print(f"Built patch against {BASE} and source archive: {len(relative)} files; no .env or Git index changes")


if __name__ == "__main__":
    main()
