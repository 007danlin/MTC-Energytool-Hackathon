# Go Backend Architecture

## Scope

This document defines the backend boundary for the Energytool consultation prototype. The existing Python code owns retrieval, answer generation, source validation, lead extraction, and consultation summaries. The Go service owns HTTP delivery, session history, persistence, access control, and orchestration. The backend must not claim that a lead was sent to a manager: the current ML contract always reports `sent: false` and there is no CRM integration.

The attached DOCX regulation and knowledge-base ZIP could not be read in this workspace because both files have malformed ZIP directory metadata. Before final acceptance, compare this architecture with a valid copy of those attachments. Existing project requirements and the ML contract are documented in `docs/ml-requirements.md` and `docs/ml-integration.md`.

## System Context

```text
Browser / frontend
      |
      | HTTPS, JSON, /api/v1
      v
Go API service ---- PostgreSQL
      |
      | internal HTTP, bounded timeout
      v
Python consultation service
      |-- retrieval over knowledge base
      |-- OpenAI-compatible model API
      `-- validated answer, sources, lead, summary
```

Use a modular monolith for the Go API. Keep the Python consultation logic as a separate process behind an internal HTTP boundary; do not shell out to Python for each request or duplicate retrieval/lead validation in Go. PostgreSQL is the system of record. The existing Compose service `ml-submit` is a batch submission tool, not a consultation HTTP server, and should not be repurposed as one without an explicit adapter/service implementation.

## Responsibilities

### Go API

- Create and list only sessions the caller is authorized to access.
- Persist user and assistant messages in order.
- Serialize message processing per session or enforce optimistic version checks.
- Send the complete active-session history to the consultation service, subject to its 200-message and 100,000-character limits.
- Persist the returned answer, status, sources, lead state, summary, and elapsed time.
- Preserve the last successful lead/summary when a consultation call fails.
- Expose manager lead views only to authorized manager roles, if authentication is in scope.
- Apply request limits, deadlines, redacted structured logs, and health checks.

### Python consultation service

- Own retrieval, prompting, model calls, answer status, citation validation, lead evidence validation, and summary creation.
- Accept the contract from `docs/ml-integration.md` and return its versioned result.
- Remain stateless between calls; Go owns history and passes the active session state.

### PostgreSQL

- Persist sessions, messages, consultation results, and lead state/evidence.
- Retain archived sessions while ensuring a new session never receives another session's history or contacts.

## Go Package Layout

```text
backend/
  cmd/api/main.go
  internal/
    config/                 environment parsing and validation
    domain/                 Session, Message, Lead, ConsultationResult
    httpapi/
      router.go
      handlers/             request/response mapping only
      middleware/           request ID, recovery, auth, limits
    service/                use cases and session-level serialization
    repository/              persistence interfaces
    postgres/                PostgreSQL implementations and migrations
    consultationclient/      typed HTTP client for Python service
  migrations/
  Dockerfile
  go.mod
```

Keep handlers thin. Services depend on repository and consultation-client interfaces so tests can substitute fakes. Do not place domain validation or SQL in handlers.

## Data Model

Use UUID primary keys and UTC timestamps. Suggested tables:

```text
sessions(id, owner_id nullable, status, version, created_at, updated_at, closed_at nullable)
messages(id, session_id, sequence, role, content, created_at)
consultation_results(id, session_id, message_id, schema_version, status, answer,
                     sources_json, summary_json, elapsed_ms, created_at)
leads(id, session_id unique, full_name nullable, phone nullable, company nullable,
      requested, declined, status, updated_at)
lead_evidence(id, lead_id, field_name, message_id, quote, created_at)
```

Add indexes on `(session_id, sequence)`, `(owner_id, updated_at)`, and lead status/update time. Keep source and summary JSON as JSONB initially; promote fields to columns only when query/reporting needs justify it. Use a transaction for appending the user message, storing the consultation result, appending the assistant message, and updating lead state. Do not hold a database transaction open while waiting for the model: persist the user message first, call ML, then commit the result in a second transaction. On ML failure, retain the user message and record a technical result without overwriting the last successful lead.

## HTTP API (v1)

- `GET /health/live`: process liveness; no dependency probes.
- `GET /health/ready`: database and consultation-service reachability suitable for deployment readiness.
- `POST /api/v1/sessions`: create an isolated conversation.
- `GET /api/v1/sessions/{session_id}`: session metadata for its owner.
- `POST /api/v1/sessions/{session_id}/messages`: append a user turn and return the consultation result.
- `GET /api/v1/sessions/{session_id}/messages`: ordered history.
- `GET /api/v1/sessions/{session_id}/lead`: current lead state.
- `GET /api/v1/leads`: manager-only paginated lead list, only if manager UI/auth is required.
- `GET /api/v1/leads/{lead_id}`: manager-only lead detail, only if required.

The full request/response shapes are in `docs/openapi.yaml`. Clients cannot supply `assistant` or `system` messages through the append endpoint. A new session has a new ID and starts with no inherited lead state.

## Message Processing

1. Authenticate and authorize the caller when authentication is enabled.
2. Validate content size and session ownership; acquire a per-session lock or compare the session version.
3. Persist the user message and load the complete ordered history and current lead state.
4. Call the consultation service with a deadline shorter than the inbound request deadline.
5. Validate response schema/version and safe status values. Treat returned text as untrusted content.
6. Persist the assistant message and result, plus updated lead/evidence, atomically.
7. Return the result. If the ML call fails, return a typed technical error and leave prior successful lead data intact.

Use a bounded connection pool and concurrency limit for model calls. Do not blindly retry a consultation POST: it can repeat model charges and create duplicate assistant turns. Add an idempotency key or client message ID before enabling retries. The current model client already has its own bounded retry behavior for transient provider failures.

## Security and Reliability

- Keep the Python service on a private Compose network; do not publish its port externally.
- Read secrets only from environment/secret mounts. Never include tokens, API keys, raw request content, phone numbers, or model response bodies in logs.
- Limit request body size and enforce the ML contract's history caps.
- Use parameterized SQL, context-aware queries, and explicit HTTP timeouts.
- Escape answer/source text in the frontend; never render it as trusted HTML.
- Do not expose internal error details to callers. Use stable error codes and request IDs.
- Keep `sent=false` until an actual manager/CRM delivery integration exists.
- For demo-only deployment, authentication may be omitted only if the app is not internet-exposed and the limitation is documented. Otherwise use the team's agreed identity mechanism; do not invent local credentials or hardcode secrets.

## Delivery Plan

1. Validate the regulation and knowledge-base files; confirm authentication, manager workflow, and deployment expectations with the team.
2. Agree on the internal Python HTTP contract and add an adapter around the existing `integration.respond_json` function. The current repository does not yet provide this HTTP service.
3. Create Go module, config, router, health endpoints, typed DTOs, and contract tests.
4. Add PostgreSQL migrations and repository implementations.
5. Implement session creation/history and per-session message serialization.
6. Implement the bounded Python consultation client and the end-to-end message use case.
7. Persist lead/evidence/results and implement any authorized manager endpoints.
8. Add Compose integration without breaking the existing ML batch-submit workflow.
9. Verify unit, integration, security, and full demo scenarios: new session isolation, lead collection/correction/withdrawal, concurrent sessions, same-session concurrency, and ML outage/recovery.
10. Document startup, environment variables, API examples, and known limitations.

## Decisions Still Requiring Team Confirmation

- Authentication provider and whether users/manager roles are part of the demo.
- Whether manager lead browsing is required for judging, and whether a real CRM/email handoff exists.
- Whether PostgreSQL is available in the target deployment; it is the recommended persistence layer.
- The final Python service endpoint and whether it will be hosted in the same Compose project.
- Valid copies of the attached regulation and knowledge-base archive, because the uploaded files in this workspace are unreadable.