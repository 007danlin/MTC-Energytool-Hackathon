"""One-command reproducible local release checks (no live model required)."""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_submission import build
from tools.evaluate import evaluate
from tools.smoke_submission import smoke


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker", action="store_true", help="Also build and test the Compose service")
    parser.add_argument("--python-compat", metavar="IMAGE", help="Also test the packaged runtime on a Python Docker image")
    args = parser.parse_args(argv)
    runtime_suite = unittest.TestLoader().discover(str(ROOT / "tests"), pattern="test_*.py")
    host_suite = unittest.TestLoader().discover(str(ROOT / "tools/host_tests"), pattern="test_*.py")
    suite_counts = {"runtime": runtime_suite.countTestCases(),
                    "host_harness": host_suite.countTestCases()}
    suite = unittest.TestSuite([runtime_suite, host_suite])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        return 1
    offline = evaluate(ROOT / "data", "offline", ROOT / "reports/private")
    if offline["protocol_pass"] != 30 or offline["retrieval_coverage_pass"] != 18:
        print(json.dumps(offline, ensure_ascii=False, indent=2))
        return 1
    archive = ROOT / "artifacts/daniel-submission.zip"
    manifest = build(archive)
    isolated = smoke(archive, ROOT / "data")
    report = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "python": sys.version.split()[0], "unit_tests_passed": result.testsRun,
              "unit_test_suites": suite_counts,
              "offline": offline, "isolated_zip": isolated,
              "zip_bytes": manifest["bytes"], "zip_sha256": manifest["sha256"],
              "live_model_verified": False, "platform_submission_verified": False,
              "team_backend_integration_verified": False}
    if args.docker:
        from tools.smoke_docker import smoke_docker
        report["docker"] = smoke_docker()
    if args.python_compat:
        from tools.check_python_compat import check_python_compat
        report["python_compatibility"] = check_python_compat(args.python_compat)
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
