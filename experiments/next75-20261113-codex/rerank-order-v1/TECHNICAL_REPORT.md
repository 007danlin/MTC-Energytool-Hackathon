# N7 technical packaging — research only

Archive: `mts-energytool-n7-focus-order-20261113.zip`. Size: **42,695 bytes**. SHA-256: `ed04950717ce270d8fb41ef5e60b99ddd130b427488beb6812d89596fe868cc1`.

This archive is **not recommended pending review of actual paired responses**. No platform submission was made. The packaging task performed zero real-model calls and did not touch the running Qwen service.

## Exact bytes and preservation

- 13 root files, no evaluation inputs, goldens, KB, weights, secrets or extra directories in the ZIP.
- Only `retrieval.py` differs from protected N2. Its reviewed SHA remains `2dc3bae6a5feeb8d9b43f24ba232575156f03dc3c7e14fdeb249f8826eb70130`.
- The existing fixed-order/fixed-timestamp builder produced two byte-identical ZIPs. Both hashes equal the release hash above.
- `final-source/` was extracted from the release ZIP. Every extracted file matches the reviewed candidate bytes; checked again after validation. Full file hashes: `technical/archive-source-proof.json` and the release `.manifest.json`.
- Protected N2 ZIP remains `a22d786f895257e14fb89e747a674cd419be0d711ed43b834fb9442ef3b6ac9b`. Candidate runtime, old results and winner were not modified.
- N7 starts from exact N2, so the separate N6 context-overflow correction is not included.

## Available validation

The existing N2/N6 acceptance harness was reused against the final ZIP: **47/47 passed**, 136.3 seconds. It exercises the 209-row known input set plus tricky CSV, import/schema/environment rules, multiline and JSON dialogue, ID isolation, 429/503, rejected hints, output-token caps, truncated/empty responses, inline thinking, context-window shrink, transport timeout/connection-close, deadline/fallback and missing configuration. These are scripted mock responses, not model accuracy results.

Runs used native macOS Python 3.14 and an explicit alternate Python 3.12. Python 3.9 grammar was checked by AST; actual Python 3.9/Linux execution is not claimed. No new dependencies were installed.

The existing source-set audit was adapted only to load `final-source/retrieval.py` and save its result separately: **202/202 known/viewed cases** preserve exact `(source_id,text)` multisets, system prompts, prompt character lengths and explicit relative-reference directions. Placement diagnostics: {'earlier': 174, 'same': 28, 'later': 65}; these are not answer-quality scores.

An additional static shrinking check used the fixed four diagnostic families and twelve viewed-panel questions at allowed prompt sizes 90k/75k/65k/55k: **64/64 case-limit pairs** preserve the source multiset on every shrink iteration, identical iteration budgets, mode availability and character counts. In 16 pairs docs did not fit in either version, and 23 pairs required multiple selection iterations. No claim that unavailable docs produced a correct fallback answer.

The 17 unchanged N6 targeted cap tests were not repeated. Candidate checks had no failures. An initial read-only lookup used the wrong filename `acceptance.py`; it was corrected to `accept.py` before the acceptance run. Raw logs and reports are retained.

## Evidence

- `technical/TECHNICAL_SUMMARY.json` — result and limitations.
- `technical/archive-source-proof.json` — exact input/output hashes and N2 comparison.
- `technical/acceptance/acceptance.json`, `technical/acceptance-runner.log` — all 47 outcomes.
- `technical/final-source-preservation.json` — 202 case details on extracted code.
- `technical/final-shrink-preservation.json`, `technical/check_final_shrink.py` — 64 shrink checks.
- `measure_final_source.py`, `technical/final-source-measure-meta.json` — isolated path adaptation of the existing audit.

A valid CSV or nonempty grounded fallback is not a correct consultation by itself. The mock run does not measure platform capacity, real inference throughput, public Score or private transfer. Ordering can still introduce factual regressions despite exact source preservation; those require actual paired review.
