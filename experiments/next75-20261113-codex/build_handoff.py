"""Package the continuation and original evidence, excluding weights/environments.

The original handoff is included unchanged as a nested archive. Extract it into
continuation/handoff to restore the relative paths used by the diagnostics.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--original", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parent
    output = a.output.resolve()
    excluded_parts = {"handoff", "__pycache__", ".git", "venv", ".venv", "weights",
                      "tokenizer-preflight", ".cache", "hf-cache", "pip-cache", "node_modules"}
    files = []
    excluded = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if (path.is_symlink() or any(part in excluded_parts for part in rel.parts)
                or path.resolve() == output or path.name.startswith(".env") or path.name == ".DS_Store"
                or path.suffix in (".safetensors", ".gguf", ".pyc", ".incomplete")
                or (rel.parts[0] == "release" and "handoff" in path.name)):
            excluded.append(str(rel))
            continue
        files.append((path, "continuation/" + rel.as_posix()))
    files.append((a.original.resolve(), "continuation/previous-handoff.zip"))
    manifest = {"files": [], "exclusions": excluded,
                "note": "Public model weights, Python environment and caches are intentionally excluded; the original handoff is included byte-for-byte."}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path, name in files:
            raw = path.read_bytes()
            manifest["files"].append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 13, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_STORED if path == a.original.resolve() else zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
        info = zipfile.ZipInfo("MANIFEST.json", date_time=(2026, 11, 13, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, json.dumps(manifest, ensure_ascii=False, indent=2).encode())
    with zipfile.ZipFile(output) as z:
        for item in manifest["files"]:
            raw = z.read(item["path"])
            assert len(raw) == item["bytes"]
            assert hashlib.sha256(raw).hexdigest() == item["sha256"]
    result = {"archive": str(output), "bytes": output.stat().st_size,
              "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
              "verified_files": len(manifest["files"]), "excluded_files": len(excluded)}
    Path(str(output) + ".json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
