# Energytool Go Backend (prototype MVP)

This is a standalone Go HTTP backend for the final web prototype. It does not replace the Python `solution.py` platform submission and does not alter the existing root-level Compose or Python files.

## Implemented

- Session create/list/get/close and message history endpoints.
- New sessions have isolated context; all session history is retained locally.
- Per-session request serialization and the Python contract's 200-message / 100,000-character input limits.
- Typed HTTP client for an internal Python consultation service using `POST /respond` and the existing contract.
- Lead state, sources, response timing and summary pass through to the chat/debug UI.
- Technical fallback preserves prior lead and summary; no claim is made that a lead was delivered.
- Operator endpoints for specialist requests and reviewed knowledge require `X-Operator-ID`, `X-Operator-Role`, and `X-Operator-Token`.
- Approved/revoked knowledge is rendered to an atomic versioned snapshot at `EXPERT_KB_SNAPSHOT`.
- Set `OPERATOR_TOKEN` in the runtime environment; the default Compose value is only for loopback demo use and must be replaced for any remote presentation.
- Idempotent message/application writes via `client_request_id` or `Idempotency-Key`; conflicting reuse is rejected.
- Request result lookup via `GET /api/v1/sessions/{sessionID}/requests/{requestID}` after an uncertain network outcome.
- Atomic, mode-0600 JSON-file persistence for a local prototype; the store interface can be replaced with PostgreSQL.
- Health endpoints, request IDs, bounded request sizes and graceful shutdown.

## Run

```sh
cd backend
BACKEND_ADDR=:8080 \
BACKEND_STORE_PATH=./var/sessions.json \
ML_SERVICE_URL=http://127.0.0.1:8090 \
ML_TIMEOUT=250s \
go run ./cmd/api
```

`ML_SERVICE_URL` must point to a separately running Python HTTP adapter exposing `POST /respond` and `GET /health/ready`, and accepting the request/response schema in the root `docs/ml-integration.md`. The adapter is implemented in root-level `consultation_http.py`. See `docs/web-stack.md` for the integrated launch. If the URL is omitted, the API remains usable for session management and returns a clearly typed technical fallback for chat requests; readiness returns HTTP 503.

The JSON file store is intended for local/demo use only. It is not multi-process safe and is not a substitute for PostgreSQL in a shared deployment. The prototype currently has no authentication; do not expose it to the public internet until an agreed identity and authorization mechanism is implemented.

## API quick start

```sh
curl -sS -X POST http://localhost:8080/api/v1/sessions
curl -sS -X POST http://localhost:8080/api/v1/sessions/SESSION_ID/messages \
  -H 'Content-Type: application/json' \
  -d '{"content":"У нас несколько арендаторов. Как начать учет?"}'
curl -sS http://localhost:8080/api/v1/sessions/SESSION_ID/messages
curl -sS http://localhost:8080/api/v1/sessions/SESSION_ID/lead
curl -sS http://localhost:8080/health/ready
```

Routes:

- `GET /health/live`, `GET /health/ready`
- `POST /api/v1/sessions`, `GET /api/v1/sessions`, `GET /api/v1/sessions/{sessionID}`
- `POST /api/v1/sessions/{sessionID}/messages`, `GET /api/v1/sessions/{sessionID}/messages`
- `GET /api/v1/sessions/{sessionID}/requests/{requestID}`
- `POST /api/v1/sessions/{sessionID}/close`, `GET /api/v1/sessions/{sessionID}/lead`
- `POST /api/v1/sessions/{sessionID}/application` — persist the reviewed contact form and summary independently of ML state; see `../docs/consultation-ui.md`.

All user and assistant messages are saved. Close marks a session read-only without deleting it. Each assistant message preserves its own `response` with `elapsed_ms`, `sources`, and `debug`, including after restart. `elapsed_ms` measures the call to the consultation service even when it fails; it excludes browser network time. The original ML processing time is retained in `debug.ml_elapsed_ms` only when available. `sources` contains validated citations selected for the answer; `debug.retrieved_sources` is the supplied context and does not imply every fragment was cited. Empty citations do not by themselves prove that retrieval found nothing.

For application retries, send `client_request_id` in JSON, `Idempotency-Key` as a header, or `client_request_id` as a query parameter. Reusing an ID with an identical payload replays the stored result; reusing it with different data returns `409 request_id_conflict`.

## Verify

```sh
cd backend
gofmt -w $(find . -name '*.go' -type f)
go test ./...
go test -race ./...
go build ./cmd/api
```
