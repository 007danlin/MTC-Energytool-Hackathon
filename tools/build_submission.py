"""Build a deterministic allowlisted ZIP; never recurse over the workspace."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
FILES = ("solution.py", "settings.py", "llm_client.py", "contracts.py", "dialogue.py",
         "retrieval.py", "prompts.py", "consultant.py", "requirements.txt")


def build(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = []
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name in FILES:
            raw = (ROOT / name).read_bytes()
            if name.endswith(".py"):
                ast.parse(raw, filename=name)
            if re.search(rb"sk-[A-Za-z0-9_-]{20,}", raw):
                raise ValueError("Possible credential in runtime code")
            info = ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, raw)
            manifest.append({"file": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(FILES)
    if output.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("ZIP exceeds platform limit")
    summary = {"zip": output.name, "bytes": output.stat().st_size,
               "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "files": manifest}
    output.with_suffix(".manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "artifacts/daniel-submission.zip"))
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))
