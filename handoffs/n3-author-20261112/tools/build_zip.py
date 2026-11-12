#!/usr/bin/env python3
"""Reproducible submission archive: root files only, fixed order and timestamps."""
import argparse, hashlib, json, zipfile
from pathlib import Path

FILES = ["solution.py", "settings.py", "llm_client.py", "consultant.py", "prompts.py", "prompts_a2.py", "dialogue_n1.py",
         "fewshot.py", "retrieval.py", "retrieval_a2.py", "dialogue.py", "contracts.py", "requirements.txt"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--set", action="append", default=[], help="name=value: override a default of the Settings dataclass in this build")
    a = p.parse_args()
    src, out = Path(a.source), Path(a.output)
    overrides = dict(item.split("=", 1) for item in a.set)

    def content(name):
        data = (src / name).read_bytes()
        if name == "settings.py" and overrides:
            import re
            text = data.decode("utf-8")
            for key, value in overrides.items():
                pattern = re.compile(r"^(    %s: (?:str|int|bool|float) = )([^#\n]*?)(\s*(?:#.*)?)$" % re.escape(key), re.M)
                if not pattern.search(text):
                    raise SystemExit("No default named " + key)
                literal = value if re.fullmatch(r"True|False|-?\d+(?:\.\d+)?", value) else '"%s"' % value
                text = pattern.sub(lambda m: m.group(1) + literal + m.group(3), text, count=1)
            data = text.encode("utf-8")
        return data
    out.parent.mkdir(parents=True, exist_ok=True)
    present = sorted(x.name for x in src.iterdir() if x.is_file() and not x.name.startswith("."))
    if sorted(FILES) != present:
        raise SystemExit(f"Unexpected source content: {sorted(set(present) ^ set(FILES))}")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in FILES:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, content(name))
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    manifest = {"archive": out.name, "sha256": digest, "bytes": out.stat().st_size, "default_overrides": overrides,
                "files": [{"name": n, "sha256": hashlib.sha256(content(n)).hexdigest(),
                           "bytes": len(content(n))} for n in FILES]}
    Path(str(out) + ".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"archive": str(out), "sha256": digest, "bytes": manifest["bytes"]}))


if __name__ == "__main__":
    main()
