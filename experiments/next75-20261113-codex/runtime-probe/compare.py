import sys
sys.dont_write_bytecode = True
from collections import Counter
import difflib
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
exact = json.loads((root / "exact-results.json").read_text())
local = json.loads((root / "local-results.json").read_text())
early = json.loads((root / "patched-results.json").read_text())
traces = {name: [json.loads(line) for line in (root / f"{name}-http.jsonl").read_text().splitlines()] for name in ("exact", "local")}
checks = {}
unchanged = ("healthy", "output-cap", "cap-with-window-fitting", "ambiguous", "ambiguous-numbers", "context-only", "context-only-below-window", "context-only-below-window-low", "mixed-413", "generic-400", "generic-404", "generic-422", "http-413")
for name in unchanged:
    left = [t["raw_payload_utf8"] for t in traces["exact"] if t["scenario"] == name]
    right = [t["raw_payload_utf8"] for t in traces["local"] if t["scenario"] == name]
    assert left == right, name
    checks[name + "_request_bytes_identical"] = True
    assert exact[name] == local[name], name + " response metadata"
    checks[name + "_response_metadata_identical"] = True
for name in ("mixed", "mixed-low", "mixed-retry", "consultant"):
    left = [t["raw_payload_utf8"] for t in traces["exact"] if t["scenario"] == name]
    right = [t["raw_payload_utf8"] for t in traces["local"] if t["scenario"] == name]
    assert left[:-1] == right[:-1], name
    assert exact[name]["remembered_cap"] == 2048
    assert local[name]["remembered_cap"] is None
    checks[name + "_first_row_bytes_identical_and_no_global_cap"] = True
assert exact["consultant"]["prompt_chars"] == local["consultant"]["prompt_chars"]
checks["consultant_all_context_sizes_unchanged"] = True

batch = {}
for variant in ("exact", "local"):
    path = root / "batch209" / f"{variant}-healthy/http.jsonl"
    batch[variant] = Counter((t["question_sha256"], t["raw_payload_utf8"]) for t in (json.loads(line) for line in path.read_text().splitlines()))
assert sum(batch["exact"].values()) == sum(batch["local"].values()) == 209
assert batch["exact"] == batch["local"]
checks["healthy209_body_bytes_equal_by_question_including_multiplicity"] = True

source = root.parent / "handoff/winner/source"
changed = [p.name for p in source.iterdir() if p.is_file() and p.read_bytes() != (root / "candidate-local" / p.name).read_bytes()]
assert changed == ["llm_client.py"], changed
checks["changed_runtime_files"] = changed
winner = root.parent / "handoff/winner/mts-energytool-n2-docs.zip"
checks["winner_sha256"] = hashlib.sha256(winner.read_bytes()).hexdigest()
assert checks["winner_sha256"] == "a22d786f895257e14fb89e747a674cd419be0d711ed43b834fb9442ef3b6ac9b"
for candidate in ("candidate", "candidate-local"):
    patch = "".join(difflib.unified_diff((source / "llm_client.py").read_text().splitlines(keepends=True), (root / candidate / "llm_client.py").read_text().splitlines(keepends=True), fromfile="a/llm_client.py", tofile="b/llm_client.py"))
    (root / f"{candidate}.patch").write_text(patch)
(root / "comparison.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(checks, ensure_ascii=False, indent=2))
print("consultant exact", json.dumps(exact["consultant"], ensure_ascii=False))
print("consultant early-raise", json.dumps(early["consultant"], ensure_ascii=False))
print("consultant local", json.dumps(local["consultant"], ensure_ascii=False))
