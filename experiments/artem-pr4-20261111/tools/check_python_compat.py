"""Test the actual packaged runtime on a selectable official Python container."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def check_python_compat(image="python:3.9-slim"):
    archive = ROOT / "artifacts/daniel-submission.zip"
    container = "energytool-python-check-" + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix="energytool-python-check-") as folder:
        runtime = Path(folder)
        with ZipFile(archive) as bundle:
            if any("/" in name or "\\" in name or name.startswith(".") for name in bundle.namelist()):
                raise ValueError("Expected root-only submission archive")
            bundle.extractall(runtime)
        # Backend adapter is used by contract tests, but is not needed by solution.py.
        shutil.copyfile(ROOT / "integration.py", runtime / "integration.py")
        args = ["docker", "run", "--rm", "--name", container, "--network", "none",
                "--volume", str(runtime) + ":/app:ro", "--volume", str(ROOT / "tests") + ":/tests:ro",
                "--workdir", "/app", "--env", "PYTHONDONTWRITEBYTECODE=1", image,
                "python", "-c", "import sys,unittest; print(sys.version.split()[0], flush=True); "
                "suite=unittest.defaultTestLoader.discover('/tests'); "
                "result=unittest.TextTestRunner().run(suite); sys.exit(0 if result.wasSuccessful() else 1)"]
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=180)
            if result.returncode:
                raise RuntimeError("Python compatibility check failed:\n" + result.stderr[-6000:])
            match = re.search(r"Ran (\d+) tests?", result.stderr)
            if not match:
                raise RuntimeError("No test results returned")
        finally:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=20)
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "image": image,
              "python": result.stdout.strip().splitlines()[0], "tests_passed": int(match[1]),
              "zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "exit_code": result.returncode}
    (ROOT / "reports/python-compatibility.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(check_python_compat(), indent=2))
