#!/usr/bin/env python3
"""Technical acceptance of the exact bytes of a submission ZIP against the mock API (no language model)."""
import ast, csv, hashlib, json, os, sys, zipfile, shutil, subprocess, glob
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scenario import scenario, KB
from paths import ALLOWED, all_questions

ZIP = sys.argv[1]
OUT = sys.argv[2]
Path(OUT).mkdir(parents=True, exist_ok=True)
ALL = all_questions(Path(OUT) / "all_questions.csv")
results = []


def check(name, condition, detail=""):
    results.append({"check": name, "ok": bool(condition), "detail": detail})
    print(("PASS " if condition else "FAIL ") + name + (" — " + str(detail) if detail else ""), flush=True)


def clean(r, rows):
    c = r.get("csv") or {}
    return r.get("exit_code") == 0 and c.get("rows") == rows and not c.get("problems") and c.get("technical_stubs") == 0


# ---------- static checks on the archive ----------
raw = Path(ZIP).read_bytes()
z = zipfile.ZipFile(ZIP)
names = z.namelist()
check("zip: size <= 128 MB", len(raw) <= 128 * 1024 * 1024, f"{len(raw)} bytes")
check("zip: root files only, no folders", all("/" not in n and not n.startswith(".") for n in names), names)
check("zip: solution.py and requirements.txt present", {"solution.py", "requirements.txt"} <= set(names))
check("zip: no data, secrets or indexes", all(n.endswith(".py") or n == "requirements.txt" for n in names))
req = [l for l in z.read("requirements.txt").decode().splitlines() if l.strip() and not l.strip().startswith("#")]
allowed = {l.strip() for l in open(ALLOWED) if l.strip()}
check("requirements: only allowed pinned packages", all(l in allowed for l in req), req or "standard library only")
py39 = True
third_party = set()
import sys as _s
std = set(_s.stdlib_module_names)
local = {n[:-3] for n in names if n.endswith(".py")}
for n in names:
    if n.endswith(".py"):
        src = z.read(n).decode("utf-8")
        try:
            tree = ast.parse(src, feature_version=(3, 9))
        except SyntaxError as e:
            py39 = False
            print("   syntax", n, e)
            continue
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods = [(node.module or "").split(".")[0]]
            for m in mods:
                if m and m not in std and m not in local:
                    third_party.add(m)
        for bad in ("pip install", "subprocess", "os.system", "eval(", "exec("):
            if bad in src:
                third_party.add("FORBIDDEN:" + bad + "@" + n)
check("python: syntax valid for Python 3.9 grammar", py39)
check("python: imports are stdlib or root modules; no pip/subprocess/eval", not third_party, sorted(third_party))
secrets = [n for n in names if any(k in z.read(n).decode("utf-8", "ignore") for k in ("sk-", "Bearer ey", "api_key=", "hf_"))]
check("zip: no key-like strings", not secrets, secrets)
hard = [n for n in names if n.endswith(".py") and any(k in z.read(n).decode() for k in ("qwen", "Qwen", "http://", "https://", "localhost", "127.0.0.1"))]
check("code: no hardcoded model identifier or service address", not hard, hard)

n_all = sum(1 for _ in csv.DictReader(open(ALL, encoding="utf-8-sig")))
import re as _re
# A build whose default is the compact context without reasoning never meets the reasoning-length scenarios:
# for it the same scenarios must simply answer every row with the first call.
QUICK = bool(_re.search(r"^    quick: bool = True", z.read("settings.py").decode("utf-8"), _re.M))
BIG = "wide" if QUICK else "docs"
RETRIED = {"ok": n_all} if QUICK else {"retried": n_all}

# ---------- behaviour ----------
r = scenario("s01-normal", ZIP, ALL, OUT)
check("S01 normal run: all ids, valid CSV, no stubs", clean(r, n_all), r.get("csv"))
check("S01 key from environment in Authorization; model id from environment", r["mock"]["auth_ok"] and r["mock"]["models"] == ["mock-model"], r["mock"]["models"])
check("S01 answers single-line plain text", r["csv"]["multiline_answers"] == 0)
base_requests = r["mock"]["requests"]
check("S01 one API call per row", base_requests == n_all, base_requests)
print("   prompt chars max:", r["mock"]["prompt_chars_max"], "max_tokens:", r["mock"]["max_tokens"], "extras:", r["mock"]["extras"], "elapsed:", r["elapsed_seconds"])

r = scenario("s02b-429-long", ZIP, ALL, OUT, mock=["--fail-first", "12", "--fail-status", "429"], env=["MAX_WORKERS=3"])
check("S02b long 429 burst (4 refusals per worker): patient retries keep the first request, no row degraded",
      clean(r, n_all) and (r.get("summary") or {}).get("statuses") == {"ok": n_all}, ((r.get("summary") or {}).get("statuses"), r["mock"]["kinds"]))
r = scenario("s02-429", ZIP, ALL, OUT, mock=["--fail-first", "9", "--fail-status", "429"])
check("S02 429 burst: bounded retries recover every row", clean(r, n_all) and r["mock"]["kinds"].get("injected") == 9, r["mock"]["kinds"])
r = scenario("s03-503", ZIP, ALL, OUT, mock=["--fail-first", "9", "--fail-status", "503"])
check("S03 5xx burst: bounded retries recover every row", clean(r, n_all), r["mock"]["kinds"])
r = scenario("s04-strict-low", ZIP, ALL, OUT, mock=["--strict"], env=["N1_REASONING=low", "MAX_WORKERS=4"])
check("S04 strict proxy rejects reasoning hints: hints dropped, run clean", clean(r, n_all) and r["mock"]["kinds"].get("strict", 0) + r["mock"]["kinds"].get("cap", 0) <= 40, r["mock"]["kinds"])
r = scenario("s05-cap", ZIP, ALL, OUT, mock=["--max-tokens-cap", "2048"])
check("S05 proxy caps max_tokens at platform value: falls back, run clean", clean(r, n_all) and r["mock"]["kinds"].get("cap", 0) <= 8, r["mock"]["kinds"])
r = scenario("s06-thinking-truncates", ZIP, ALL, OUT, mock=["--truncate", "thinking", "--empty-on-length"])
check("S06 thinking exhausts tokens: recovery call answers, no stubs", clean(r, n_all), (r["mock"]["kinds"], r.get("summary", {}).get("statuses")))
r = scenario("s07-always-truncated", ZIP, ALL, OUT, mock=["--truncate", "always", "--empty-on-length"], env=["MAX_WORKERS=8"])
check("S07 every generation token-limited: grounded fallback text, valid CSV, no stubs, bounded calls", clean(r, n_all) and r["mock"]["requests"] <= 3 * n_all, (r["mock"]["requests"], r.get("summary", {}).get("statuses")))
r = scenario("s08-full-overflow", ZIP, ALL, OUT, mock=["--context-limit", "60000"], env=["N1_CONTEXT=full"])
check("S08 full base over a small context window: learns the window, compact context for every row, run clean", clean(r, n_all) and r["mock"]["kinds"].get("context", 0) <= 24 and (r.get("summary") or {}).get("modes") == {"wide": n_all} and r["mock"]["requests"] <= n_all + 24, (r["mock"]["kinds"], (r.get("summary") or {}).get("modes"), (r.get("summary") or {}).get("window_chars")))
r = scenario("s08b-full-overflow-docs-fit", ZIP, ALL, OUT, mock=["--context-limit", "100000"], env=["N1_CONTEXT=full"])
check("S08b full base over a medium context window: documents for every row, run clean", clean(r, n_all) and (r.get("summary") or {}).get("modes") == {BIG: n_all} and r["mock"]["requests"] <= n_all + 24, (r["mock"]["kinds"], (r.get("summary") or {}).get("modes"), (r.get("summary") or {}).get("window_chars")))
r = scenario("s08d-docs-window", ZIP, ALL, OUT, mock=["--context-limit", "90000", "--context-detail"], env=["N1_CONTEXT=docs"])
check("S08d documents slightly over the window: sized to the stated window, documents kept for every row", clean(r, n_all) and (r.get("summary") or {}).get("modes") == {BIG: n_all} and r["mock"]["kinds"].get("context", 0) <= 8 and r["mock"]["prompt_chars_max"] < 95000, (r["mock"]["kinds"], (r.get("summary") or {}).get("window_chars")))
r = scenario("s08c-slow-large-context", ZIP, ALL, OUT, mock=["--slow-over", "60000", "--slow-delay", "5"], env=["N1_CONTEXT=full", "N1_BIG_TIMEOUT=5", "MAX_WORKERS=4"])
check("S08c large contexts time out: steps down to the compact context, complete CSV without stubs", clean(r, n_all) and (r.get("summary") or {}).get("context_at_end") == "wide" and r["elapsed_seconds"] < 90, (r["elapsed_seconds"], (r.get("summary") or {}).get("statuses")))
sm = lambda r: r.get("summary") or {}
r = scenario("s06b-long-reasoning", ZIP, ALL, OUT, mock=["--truncate", "deep", "--empty-on-length"])
check("S06b reasoning longer than the first budget: second try in the same context with 8192 tokens answers every row",
      clean(r, n_all) and r["mock"]["requests"] == (1 if QUICK else 2) * n_all and sm(r).get("statuses") == RETRIED and len(sm(r).get("modes", {})) == 1 and (QUICK or "8192" in r["mock"]["ok_by_tokens"]),
      (r["mock"]["ok_by_tokens"], sm(r).get("statuses"), sm(r).get("modes")))
r = scenario("s06c-long-reasoning-strict", ZIP, ALL, OUT, mock=["--truncate", "deep", "--empty-on-length", "--strict"])
check("S06c same with a proxy that rejects reasoning hints: hints dropped, larger budget still answers",
      clean(r, n_all) and sm(r).get("statuses") == {"retried": n_all} and r["mock"]["kinds"].get("strict", 0) <= 40, (r["mock"]["kinds"], sm(r).get("statuses")))
r = scenario("s06d-long-reasoning-cap", ZIP, ALL, OUT, mock=["--truncate", "deep", "--empty-on-length", "--max-tokens-cap", "4096"])
check("S06d proxy caps max_tokens at 4096: ladder stops at 4096, never falls to the platform value",
      clean(r, n_all) and r["mock"]["max_tokens"] == ([4096] if QUICK else [4096, 8192]) and r["mock"]["ok_by_tokens"].get("4096") == n_all and r["mock"]["kinds"].get("cap", 0) <= 8,
      (r["mock"]["max_tokens"], r["mock"]["ok_by_tokens"], r["mock"]["kinds"]))
r = scenario("s06e-loop", ZIP, ALL, OUT, mock=["--truncate", "loop", "--empty-on-length"])
check("S06e repetition loop of the first prompt: the second try (other prompt) answers every row",
      clean(r, n_all) and sm(r).get("statuses") == RETRIED, sm(r).get("statuses"))
r = scenario("s06f-tail", ZIP, ALL, OUT, mock=["--truncate", "tail", "--empty-on-length"])
check("S06f a share of token-limited rows does not change the context of the other rows",
      clean(r, n_all) and len(sm(r).get("modes", {})) == 1 and set(sm(r).get("statuses", {})) == ({"ok"} if QUICK else {"ok", "retried"}) and sm(r).get("fast_mode") == QUICK,
      (sm(r).get("statuses"), sm(r).get("modes")))
r = scenario("s09-full-ok", ZIP, ALL, OUT, env=["N1_CONTEXT=full"])
check("S09 full-base mode accepted: one call per row", clean(r, n_all) and r["mock"]["requests"] == n_all, r["mock"]["prompt_chars_max"])
r = scenario("s09b-docs", ZIP, ALL, OUT, env=["N1_CONTEXT=docs"])
check("S09b documents mode: one call per row", clean(r, n_all) and r["mock"]["requests"] == n_all, r["mock"]["prompt_chars_max"])
r = scenario("s09c-wide", ZIP, ALL, OUT, env=["N1_CONTEXT=wide"])
check("S09c compact mode: one call per row", clean(r, n_all) and r["mock"]["requests"] == n_all, r["mock"]["prompt_chars_max"])
r = scenario("s10-deadline", ZIP, ALL, OUT, mock=["--delay", "0.6"], env=["RUN_BUDGET_SECONDS=12", "MAX_WORKERS=3"])
check("S10 budget exhausted: complete valid CSV without stubs, stops near the budget", clean(r, n_all) and r["elapsed_seconds"] < 25, (r["elapsed_seconds"], r.get("summary", {}).get("statuses")))
r = scenario("s11-empty", ZIP, ALL, OUT, mock=["--empty"])
check("S11 empty content with finish=stop: recovered", clean(r, n_all), r.get("summary", {}).get("statuses"))
r = scenario("s12-think-inline-close", ZIP, ALL, OUT, mock=["--think-inline", "--close"])
ans = list(csv.DictReader(open(Path(OUT) / "s12-think-inline-close" / "submission.csv", encoding="utf-8")))
check("S12 inline <think> removed; Connection: close handled", clean(r, n_all) and not any("think" in a["answer"] or "скрытые" in a["answer"] for a in ans))
r = scenario("s13-401", ZIP, ALL, OUT, mock=["--key", "other-key"], env=["MAX_WORKERS=8"])
check("S13 HTTP 401 for every call: no retry storm, complete CSV without stubs", clean(r, n_all) and r["mock"]["requests"] <= 3 * n_all, r["mock"]["requests"])
r = scenario("s14-bad-env", ZIP, ALL, OUT, env=["MAX_TOKENS=abc", "MAX_WORKERS=100", "TOP_K=0", "TEMPERATURE=nan", "LLM_TIMEOUT=x", "RUN_BUDGET_SECONDS=", "CHUNKER=common", "EMB_MODEL=baai/bge-m3", "RERANKER_MODEL=x", "RERANKER_TOP_N=2"])
check("S14 malformed optional settings do not abort", clean(r, n_all), r["mock"]["max_tokens"])
r = scenario("s15-openai-names", ZIP, ALL, OUT, base_var="OPENAI_BASE_URL")
check("S15 OPENAI_BASE_URL accepted", clean(r, n_all))
r = scenario("s16-py311", ZIP, ALL, OUT, python=os.environ.get("ALT_PYTHON", "/usr/bin/python3.11"))
check("S16 runs under Python 3.11", clean(r, n_all))

# ---------- tricky inputs and isolation ----------
tricky = Path(OUT) / "tricky.csv"
rows = [("a-1", 'Вопрос с "кавычками", запятыми; и переносом\nстроки. Что такое ГТП?'),
        ("0002", "Здравствуйте!\nНужна солнечная станция 510 кВт.\nЕсть ли ограничения по мощности?"),
        ("x3", '[{"role":"user","content":"У нас 900 кВт."},{"role":"assistant","content":"Понял."},{"role":"user","content":"На опт можно?"}]'),
        ("x4", "Пользователь: Мой телефон +7 999 000-00-01, компания ООО «СЕКРЕТ-АЛЬФА».\nАссистент: Спасибо.\nПользователь: Сколько стоит платформа?"),
        ("x5", "Сколько стоит платформа?"),
        ("x6", "Сколько стоит платформа?"),
        ("x7", "😀 emoji и юникод ₽ кВт·ч — что вы делаете?"),
        ("x8", "А" * 30000 + " что это?"),
        ("x9", "   Ассистент: реплика без пользователя в начале? Нет, это просто текст.")]
with open(tricky, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f, lineterminator="\r\n")
    w.writerow(["question", "id"])   # reversed column order + BOM + CRLF
    w.writerows((q, i) for i, q in rows)
r = scenario("s17-tricky", ZIP, str(tricky), OUT, keep_requests=True)
c = r.get("csv") or {}
check("S17 tricky CSV (BOM, CRLF, reversed columns, quotes, newlines, JSON dialogue, 30k chars)", r.get("exit_code") == 0 and c.get("rows") == len(rows) and c.get("technical_stubs") == 0 and not [p for p in c.get("problems", []) if "ids differ" not in p], c)
got = list(csv.DictReader(open(Path(OUT) / "s17-tricky" / "submission.csv", encoding="utf-8")))
check("S17 output ids equal input ids in order", [g["id"] for g in got] == [i for i, _ in rows])
bodies = [json.load(open(p, encoding="utf-8")) for p in sorted(glob.glob(str(Path(OUT) / "s17-tricky" / "requests" / "*.json")))]
leak = [b for b in bodies if "СЕКРЕТ-АЛЬФА" in json.dumps(b, ensure_ascii=False)]
check("S17 isolation: contact data of one id appears only in its own request", len(leak) == 1, len(leak))
hashes = [hashlib.sha256(json.dumps(b, ensure_ascii=False, sort_keys=True).encode()).hexdigest() for b in bodies]
twice = [h for h in set(hashes) if hashes.count(h) == 2]
check("S17 identical questions under different ids produce identical requests (no shared state)", len(bodies) == len(rows) and len(set(hashes)) == len(rows) - 1 and len(twice) == 1, (len(bodies), len(set(hashes))))
multi = [b for b in bodies if "510 кВт" in b["messages"][-1]["content"]]
check("S17 multi-line question reaches the model whole", len(multi) == 1 and "Есть ли ограничения по мощности?" in multi[0]["messages"][-1]["content"] and "Здравствуйте!" in multi[0]["messages"][-1]["content"])
shutil.rmtree(Path(OUT) / "s17-tricky" / "requests", ignore_errors=True)

# legacy input names and absolute DATA_DIR are exercised directly
import tempfile
work = Path(tempfile.mkdtemp())
with zipfile.ZipFile(ZIP) as zz:
    zz.extractall(work / "app")
(work / "inputs").mkdir()
shutil.copyfile(ALL, work / "inputs" / "train.csv")
shutil.copyfile(KB, work / "inputs" / "kb.zip")
port_file = work / "port"
srv = subprocess.Popen([sys.executable, str(Path(__file__).resolve().parent / "mock_api.py"), "--record", str(work / "rec"), "--port-file", str(port_file)])
import time
for _ in range(100):
    if port_file.exists() and port_file.read_text().strip():
        break
    time.sleep(0.05)
env = {"PATH": os.environ["PATH"], "BASE_URL": f"http://127.0.0.1:{port_file.read_text()}/v1", "OPENAI_API_KEY": "mock-key",
       "GEN_MODEL": "mock-model", "DATA_DIR": str(work / "inputs"), "PYTHONDONTWRITEBYTECODE": "1"}
p = subprocess.run([sys.executable, "solution.py"], cwd=work / "app", env=env, capture_output=True, text=True)
srv.terminate(); srv.wait()
ok = p.returncode == 0 and (work / "app" / "submission.csv").is_file() and sum(1 for _ in csv.reader(open(work / "app" / "submission.csv", encoding="utf-8"))) == n_all + 1
check("S18 legacy names train.csv/kb.zip, absolute DATA_DIR, BASE_URL/OPENAI_API_KEY/GEN_MODEL", ok, p.stderr[-300:] if not ok else "")
logs = p.stderr + p.stdout
check("S18 logs contain no key, address, question or answer text", "mock-key" not in logs and "127.0.0.1" not in logs and "кВт" not in logs and "Ответ-" not in logs)
p2 = subprocess.run([sys.executable, "solution.py"], cwd=work / "app", env={"PATH": os.environ["PATH"]}, capture_output=True, text=True)
check("S19 missing API configuration: clear non-zero exit, no traceback", p2.returncode == 2 and "Traceback" not in p2.stderr, p2.stderr.strip()[:120])
shutil.rmtree(work, ignore_errors=True)

summary = {"zip": ZIP, "zip_sha256": hashlib.sha256(raw).hexdigest(), "passed": sum(r_["ok"] for r_ in results), "total": len(results), "results": results}
Path(OUT, "acceptance.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
print(f"ACCEPTANCE {summary['passed']}/{summary['total']}  sha256={summary['zip_sha256']}")
sys.exit(0 if summary["passed"] == summary["total"] else 1)
