"""Build and verify the actual Compose service without real credentials or LLM calls."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.smoke_submission import archive_stage_counts, assert_metrics


def command(args, *, timeout=60, check=True):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args[:4])}\n"
                           + result.stdout[-3000:] + result.stderr[-3000:])
    return result


def smoke_docker(*, image="energytool-ml:validation", skip_build=False):
    archive = ROOT / "artifacts/daniel-submission.zip"
    plan = archive_stage_counts(archive, ROOT / "data")
    selector_errors = int(any(item["selector"] for item in plan.values()))
    command(["docker", "version", "--format", "{{.Server.Version}}"])
    if not skip_build:
        # Stream build output; downloading the base image can take several minutes.
        subprocess.run(["docker", "build", "--tag", image, "."], cwd=ROOT, check=True, timeout=600)
    project = "energytool-smoke-" + uuid.uuid4().hex[:12]
    app_container, unit_container = project + "-run", project + "-unit"
    config = json.loads(command(["docker", "compose", "-f", "compose.submit.yaml", "--env-file", str(ROOT / ".env.example"),
                                 "--project-name", project, "config", "--no-env-resolution",
                                 "--no-interpolate", "--format", "json"]).stdout)
    config["name"] = project
    service = config["services"]["ml-submit"]
    service.pop("build", None)
    service.pop("env_file", None)
    service["image"] = image
    service["environment"] = {
        "DATA_DIR": "/data", "LLM_BASE_URL": "http://mock-llm:8080/v1",
        "LLM_API_KEY": "local-mock-key", "LLM_MODEL": "local-mock-model",
        "MAX_WORKERS": "3", "LLM_TIMEOUT": "15", "LLM_ATTEMPTS": "2",
    }
    config["networks"] = {"default": {"internal": True}}
    config["services"]["mock-llm"] = {
        "image": image,
        "command": ["python", "/fixtures/smoke_submission.py", "--serve", "--rate-limit-once"]
                   + (["--selector-error-once"] if selector_errors else []),
        "volumes": [{"type": "bind", "source": str(ROOT / "tools/smoke_submission.py"),
                     "target": "/fixtures/smoke_submission.py", "read_only": True}],
        "healthcheck": {"test": ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).read()"],
                        "interval": "1s", "timeout": "3s", "retries": 20},
        "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
    }
    with tempfile.TemporaryDirectory(prefix="energytool-docker-") as folder:
        temporary = Path(folder)
        compose_path = temporary / "compose.json"
        compose_path.write_text(json.dumps(config), encoding="utf-8")
        compose = ["docker", "compose", "--project-name", project, "-f", str(compose_path)]
        try:
            print("Checking Python tests inside the built image...", flush=True)
            unit = command(["docker", "run", "--rm", "--name", unit_container, "--network", "none",
                            "--volume", f"{ROOT / 'tests'}:/tests:ro",
                            "--volume", f"{ROOT / 'integration.py'}:/app/integration.py:ro",
                            image, "python", "-m", "unittest", "discover", "-s", "/tests"])
            match = re.search(r"Ran (\d+) tests?", unit.stderr)
            if not match or "\nOK\n" not in unit.stderr:
                raise RuntimeError("Container unit tests did not report success")
            print("Starting isolated mock API and Compose service...", flush=True)
            command(compose + ["up", "-d", "--wait", "--wait-timeout", "30", "mock-llm"])
            run = command(compose + ["run", "--name", app_container, "--no-deps", "-T", "ml-submit"])
            stats = json.loads(run.stdout.strip().splitlines()[-1])
            command(["docker", "cp", app_container + ":/app/submission.csv", str(temporary / "submission.csv")])
            with (ROOT / "data/questions.csv").open(encoding="utf-8-sig", newline="") as stream:
                ids = [row["id"] for row in csv.DictReader(stream)]
            with (temporary / "submission.csv").open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != ["id", "answer"]:
                    raise RuntimeError("Invalid output columns")
                rows = list(reader)
            if ([r["id"] for r in rows] != ids or len(ids) != len(set(ids))
                    or not all(0 < len(r["answer"]) <= 10000 and r["answer"].startswith("[MOCK]") for r in rows)):
                raise RuntimeError("Invalid output records or technical fallback instead of API response")
            if stats["statuses"] != {"answered": len(ids)}:
                raise RuntimeError("Unexpected runtime statuses")
            metrics = json.loads(command(compose + ["exec", "-T", "mock-llm", "python", "-c",
                "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/metrics').read().decode())"]).stdout)
            assert sum(item["answer"] for item in plan.values()) == len(ids)
            assert_metrics(metrics, plan, selector_failures=selector_errors, answer_rate_limits=1)
            # Execute this probe with the same service volumes, user and security options.
            probe_code = '''import hashlib,json,os,pathlib,sys
assert os.getuid()!=0
try:
    open('/data/questions.csv','ab').close()
except OSError:
    readonly=True
else:
    raise AssertionError('Input mount is writable')
files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in pathlib.Path('/app').glob('*') if p.is_file() and (p.suffix=='.py' or p.name=='requirements.txt')}
print(json.dumps({'uid':os.getuid(),'data_read_only':readonly,'python':sys.version.split()[0],'files':files}))'''
            probe = json.loads(command(compose + ["run", "--rm", "--no-deps", "-T", "ml-submit",
                                                   "python", "-c", probe_code]).stdout)
            archive = ROOT / "artifacts/daniel-submission.zip"
            with ZipFile(archive) as bundle:
                expected = {name: hashlib.sha256(bundle.read(name)).hexdigest() for name in bundle.namelist()}
            if probe.pop("files") != expected:
                raise RuntimeError("Built image code differs from the final submission ZIP")
            missing = command(["docker", "run", "--rm", "--network", "none", image], check=False)
            if missing.returncode != 2 or "Missing configuration:" not in missing.stderr:
                raise RuntimeError("Missing API configuration must produce an actionable exit code 2")
            image_info = json.loads(command(["docker", "image", "inspect", image]).stdout)[0]
            report = {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "mode": "docker_compose_mock_http", "build_verified": True,
                "image": image, "image_id": image_info["Id"],
                "platform": image_info["Os"] + "/" + image_info["Architecture"],
                "unit_tests_passed": int(match[1]), "runtime": probe,
                "rows": len(rows), "api_calls": metrics["calls"], "recovered_429": True,
                "selector_calls": metrics["selector_calls"], "answer_calls": metrics["answer_calls"],
                "selector_failures": metrics["selector_failures"], "stage_counts_exact": True,
                "selector_failure_fell_back": bool(selector_errors),
                "csv_valid": True, "exit_code": run.returncode,
                "missing_config_exit_code": missing.returncode,
                "image_matches_zip": True, "zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "live_model_verified": False,
            }
        finally:
            command(["docker", "rm", "-f", app_container, unit_container], check=False)
            command(compose + ["down", "--remove-orphans", "--volumes"])
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/docker-validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="energytool-ml:validation")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    print(json.dumps(smoke_docker(image=args.image, skip_build=args.skip_build), ensure_ascii=False, indent=2))
