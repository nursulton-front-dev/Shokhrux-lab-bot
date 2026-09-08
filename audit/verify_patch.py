"""Apply the patch to a private reconstruction of its documented baseline."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "audit/fixed-files.json").read_text())
with tempfile.TemporaryDirectory(prefix="fitness-audit-patch-") as directory:
    target = Path(directory)
    for name in manifest["sha256"]:
        result = subprocess.run(["git", "show", f'{manifest["patch_base"]}:{name}'], cwd=ROOT, capture_output=True)
        if result.returncode == 0:
            output = target / name
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(result.stdout)
    patch = ROOT / "audit/fixes.patch"
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=target, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=target, check=True)
    for name, expected in manifest["sha256"].items():
        actual = hashlib.sha256((target / name).read_bytes()).hexdigest()
        if actual != expected:
            raise AssertionError(f"Patched file differs: {name}")
    print(f'Patch applies to {manifest["patch_base"]}; all {len(manifest["sha256"])} file hashes match the tested workspace.')
