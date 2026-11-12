#!/usr/bin/env python3
"""Run the exact bytes of a submission ZIP against an OpenAI-compatible endpoint and validate the CSV.

The archive is extracted into a new empty directory; only the platform inputs are placed in DATA_DIR.
"""
import argparse, csv, hashlib, json, os, shutil, subprocess, sys, tempfile, time, zipfile
from pathlib import Path

STUBS = ("технического сбоя", "Не могу ответить по доступным фрагментам")


def validate(csv_path, questions_path):
    with open(questions_path, encoding="utf-8-sig", newline="") as f:
        ids = [r["id"] for r in csv.DictReader(f)]
    raw = Path(csv_path).read_bytes()
    raw.decode("utf-8")  # must be valid UTF-8
    problems = []
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    if header != ["id", "answer"]:
        problems.append(f"header={header}")
    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append("BOM present")
    if any(len(r) != 2 for r in rows):
        problems.append("row width != 2")
    out_ids = [r[0] for r in rows]
    if out_ids != ids:
        problems.append("ids differ from input order/content")
    if len(set(out_ids)) != len(out_ids):
        problems.append("duplicate ids")
    answers = [r[1] for r in rows if len(r) == 2]
    if any(not a.strip() for a in answers):
        problems.append("empty answer")
    if any(len(a) > 10000 for a in answers):
        problems.append("answer longer than 10000")
    stubs = sum(any(s in a for s in STUBS) for a in answers)
    return {"rows": len(rows), "problems": problems, "technical_stubs": stubs,
            "max_answer_chars": max((len(a) for a in answers), default=0),
            "multiline_answers": sum("\n" in a for a in answers),
            "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--zip", required=True)
    p.add_argument("--questions", required=True)
    p.add_argument("--kb", required=True)
    p.add_argument("--base-url", required=True)
    p.add_argument("--api-key", default="mock-key")
    p.add_argument("--model", default="mock-model")
    p.add_argument("--env", action="append", default=[], help="NAME=VALUE passed to the solution")
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--output", required=True, help="directory for submission.csv, logs and the report")
    p.add_argument("--timeout", type=float, default=1300)
    p.add_argument("--base-var", default="LLM_BASE_URL")
    a = p.parse_args()
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="zip-run-"))
    try:
        with zipfile.ZipFile(a.zip) as z:
            names = z.namelist()
            if any("/" in n or n.startswith(".") for n in names):
                raise SystemExit("Archive must contain root files only")
            z.extractall(work)
        data = work / "data"
        data.mkdir()
        shutil.copyfile(a.questions, data / "questions.csv")
        shutil.copyfile(a.kb, data / "knowledge-base.zip")
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8",
               a.base_var: a.base_url, "LLM_API_KEY": a.api_key, "LLM_MODEL": a.model, "DATA_DIR": "data"}
        for item in a.env:
            k, _, v = item.partition("=")
            env[k] = v
        started = time.monotonic()
        proc = subprocess.run([a.python, "solution.py"], cwd=work, env=env, capture_output=True, text=True, timeout=a.timeout)
        elapsed = round(time.monotonic() - started, 2)
        (out / "stdout.log").write_text(proc.stdout)
        (out / "stderr.log").write_text(proc.stderr)
        report = {"zip": a.zip, "zip_sha256": hashlib.sha256(Path(a.zip).read_bytes()).hexdigest(),
                  "archive_files": sorted(names), "exit_code": proc.returncode, "elapsed_seconds": elapsed,
                  "env": {k: v for k, v in env.items() if k not in ("PATH", "LLM_API_KEY")},
                  "leftover_files": sorted(x.name for x in work.iterdir() if x.name not in names and x.name != "data")}
        sub = work / "submission.csv"
        if sub.is_file():
            shutil.copyfile(sub, out / "submission.csv")
            report["csv"] = validate(out / "submission.csv", a.questions)
        else:
            report["csv"] = None
        try:
            report["summary"] = json.loads(proc.stdout.strip().splitlines()[-1])
        except Exception:
            report["summary"] = None
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({k: report[k] for k in ("exit_code", "elapsed_seconds", "csv", "summary")}, ensure_ascii=False))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
