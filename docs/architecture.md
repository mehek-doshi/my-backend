# Architecture

## Components

```
Browser / front end ──HTTPS──▶  API (FastAPI)  ──▶  PostgreSQL   (application data, agent runs, checkpoints, events, audit log)
                                  │   ▲                ▲
                         enqueue  │   │ results        │
                                  ▼   │                │
                               Redis (Celery broker)   │
                                  │                    │
              ┌───────────────────┴──────┐             │
              ▼                          ▼             │
        Worker (Celery)            Scheduler (Celery beat)
        runs jobs + agents         only enqueues recurring tasks
              │
              ├──▶ Orchestrator ──▶ Agents (discovery, extraction, enrichment, classification,
              │                             deduplication, guardrails, verification,
              │                             ingestion, gamification)
              ├──▶ Storage (local disk now; artifacts, certificate PDFs)
              └──▶ Integrations (Entra, Graph mail/directory/SharePoint, Teams, Buddy) behind interfaces
```

| Piece | Where in the code | Notes |
|---|---|---|
| API (REST + auth) | `app/api`, `app/core/security.py` | Thin: validates input, checks the role, calls a service, commits. |
| Orchestrator | `app/orchestrator/discovery.py` | Coordinates the discovery workflow and records run events and checkpoints. |
| Agents | `app/agents/` | Each agent does one job and can be tested alone. Agents never publish anything. |
| Services | `app/services/` | Business rules: lifecycle state machines, volunteering, artifacts, notifications, audit. |
| Worker / jobs | `app/worker/` | `jobs.py` holds the idempotent job bodies; `tasks.py` wraps them for Celery. |
| Scheduler | `app/worker/celery_app.py` (`beat_schedule`) | Separate process; schedules come from settings. |
| Database | `app/db`, `alembic/` | SQLAlchemy 2 models, one Alembic migration. |
| Storage | `app/storage/local.py` | Server-generated keys, path-traversal checked. Replace with blob storage for multi-node production. |
| Security | `app/security/` | SSRF guard, prompt-injection defences, upload validation and scanning. |

## Workflows

**Discovery** – Scheduler (every 6 h) or an admin → `DiscoverySession` + `AgentRun` (idempotency key) → worker claims the run (queued→running, compare-and-set) →
for each feed: fetch (SSRF-safe) → parse RSS/Atom → for each item: cheap duplicate check → article extraction → LLM enrichment (strict JSON schema) →
classification → guardrails → verification → stored as `open_for_volunteers` (published automatically: verified, guardrails passed, has a category, not a possible duplicate), `pending_review` (verified but no category or a possible duplicate: waits for an Admin), `unverified` or `blocked`. There is no relevance score. Admins can still approve, reject, merge or manually verify through the API.

**Contribution** – Admin invites (or an employee volunteers) → accept → volunteer (active, or waitlisted when full) + Study assignment with a deadline →
complete a stage → next stage (Study → POC → Presentation) → artifact submission → size/type/magic-byte checks on arrival → worker scan (secrets, client names, archive structure, executables) →
`pending_review` (or `quarantined`) → an Admin approves → artifact library + badges; finishing the Presentation stage issues a certificate PDF. Approved artifacts are uploaded to SharePoint by a job (if configured).

## Lifecycles (enforced in `app/services/lifecycle.py`; every other transition raises HTTP 409)

Topic: `discovered → enriched → classified → {blocked | unverified | pending_review | open_for_volunteers}`; `unverified → pending_review | rejected` (manual verification is audited);
`pending_review → open_for_volunteers | rejected | merged | unverified`; `open_for_volunteers ⇄ in_progress → archived`.
`open_for_volunteers` additionally requires `verified = true` **and** a passed guardrail record, whether it is reached automatically or by an Admin.

Artifact: `submitted → scanning → {quarantined | pending_review}`; `pending_review → approved | rejected | quarantined`; `quarantined/rejected → submitted` (only by replacing the file).
`approved` additionally requires a stored scan report with `blocked = false`. Reviewers cannot review their own artifacts.

## Reliability

* **Idempotency** – `agent_runs.idempotency_key` and `job_executions.idempotency_key` are unique. Scheduled work uses time-bucket keys, so a re-delivered or double-scheduled task does nothing the second time.
* **Duplicate execution** – status changes that claim work (`queued→running`, `submitted→scanning`, job re-claim) are single `UPDATE … WHERE status = …` statements; only one worker wins.
* **Crash recovery** – Celery `acks_late` + `reject_on_worker_lost`; a reaper job fails runs whose heartbeat is older than `JOB_LEASE_MINUTES`, re-queues artifacts stuck in `scanning`, and expires invitations.
* **Retries** – integration/scan tasks retry with exponential back-off; notification delivery retries 3 times then marks the notification `failed`. Discovery is not auto-retried: a failed run is stored and visible, per-source failures only make the run `partial`.
* **Visibility** – `agent_runs`, `agent_events` (progress feed, poll with `after_seq`), `agent_checkpoints`, `job_executions`, `audit_logs`.

## Security design

| Threat | Mitigation |
|---|---|
| Unauthenticated / wrong-role access | Every route depends on `current_user` or a role dependency (generated in `docs/api.md`); 401 vs 403 are distinct; other people's private resources return 404. |
| Dev auth leaking into production | Needs `AUTH_MODE=dev` **and** `ALLOW_DEV_AUTH=true` **and** `ENVIRONMENT != production`; `Settings` refuses to start otherwise, and `ENVIRONMENT` defaults to `production`. Mock providers and eager Celery are refused in production too. |
| Forged tokens | RS256 only, JWKS from the tenant, issuer, audience, tenant id and expiry checked, e-mail domain allow-list. Roles are re-synced from the token at every sign-in. |
| SSRF | Public IPs only (checked after DNS, connection pinned to the checked IP), no credentials/odd ports, redirects re-validated, size and content-type caps. Applies to feeds, article pages, source registration, custom topic links and repo links. |
| Prompt injection | Web text is sanitised, wrapped in `<untrusted>` blocks, scanned for instruction patterns (guardrail blocks the topic), model output must match a strict schema (`extra="forbid"`), unknown URLs/secrets in output block the topic, and **no model output can publish anything**. |
| Malicious uploads | Extension allow/deny list, magic bytes, streaming size cap, zip-bomb/traversal/executable checks, secret and client-name scanning (findings are stored redacted), quarantine, download as `application/octet-stream` + `nosniff` + CSP sandbox. **There is no antivirus engine**; scan reports say `antivirus: not_configured`. |
| Duplicate job execution | See Reliability. |
| Secrets | Environment variables only; audit details and validation errors never echo secrets. |
| Accountability | `audit_logs` for sign-ups, role changes, topic/artifact decisions, settings, sources, invitations; each row carries actor, IP and request id. |

## Data model (24 tables)

users · categories · technology_sources · topics · source_articles · topic_reviews · topic_test_cases · discovery_sessions · agent_runs · agent_checkpoints · agent_events · job_executions ·
invitations · volunteers · assignments · artifacts · moderation_records · notifications · badges · user_badges · certificates · audit_logs · app_settings · integration_state.
UUID primary keys, timezone-aware timestamps, foreign keys, indexes and CHECK/UNIQUE constraints are defined in `app/db/models` and `alembic/versions/0001_initial_schema.py`.
