# Neuleap.ai Tech Radar – backend

Python 3.11+ · FastAPI · Pydantic v2 · PostgreSQL · SQLAlchemy 2 · Alembic · Redis · Celery · Docker.

What it does: finds new technologies from RSS/Atom feeds, filters them with guardrails, verifies their sources, publishes the ones that pass, lets employees volunteer through
Study → POC → Presentation stages with deadlines, accepts **artifact** uploads that are scanned and reviewed by an **Admin** before anyone else can see them, and awards badges and certificates.
**Nothing unverified or blocked is ever published. Topics that pass verification and the guardrails open for volunteers on their own; artifacts always need an Admin's approval.**

Docs: [`docs/architecture.md`](docs/architecture.md) · [`docs/api.md`](docs/api.md) (64 endpoints, generated) · [`docs/integrations.md`](docs/integrations.md)

```
tech-radar/
  backend/       the API, worker and scheduler (one image, three commands)   → app/, alembic/, tests/
  frontend/      the earlier static front end (NOT connected to this API yet, see "Front end")
  docs/          architecture, API reference, integrations
  docker-compose.yml   .env.example
```

---

## 1. Quick start with Docker (Windows PowerShell)

Needs Docker Desktop running.

```powershell
cd tech-radar
Copy-Item .env.example .env
docker compose up --build -d
docker compose run --rm api python -m app.seed --dev-users
docker compose ps
```

Open <http://localhost:8000/docs> (interactive API; hidden when `ENVIRONMENT=production`). Check it works:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-RestMethod http://localhost:8000/api/v1/auth/me -Headers @{ "X-Dev-User" = "admin@neuleap.ai" }
```

Services: `db` (PostgreSQL 16), `redis`, `migrate` (runs `alembic upgrade head` once), `api`, `worker` (Celery), `beat` (the scheduler – run exactly one).
Logs: `docker compose logs -f api worker beat`. Stop: `docker compose down` (add `-v` to delete the data).

## 2. Run on your machine (no Docker for the Python parts)

```powershell
cd tech-radar
docker compose up -d db redis            # only PostgreSQL and Redis in Docker
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1             # if blocked:  Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements-dev.txt
Copy-Item ..\.env.example .env           # the app reads backend\.env when started from backend\
alembic upgrade head
python -m app.seed --dev-users
uvicorn app.main:app --reload
```

In two more PowerShell windows (activate the venv in each: `cd tech-radar\backend; .\.venv\Scripts\Activate.ps1`):

```powershell
celery -A app.worker.celery_app worker --loglevel=INFO --pool=solo     # background jobs  (--pool=solo is required on Windows)
celery -A app.worker.celery_app beat   --loglevel=INFO                 # the scheduler
```

No Redis yet and just want to click around? Set `CELERY_TASK_ALWAYS_EAGER=true` in `.env` – jobs then run inside the API process (development only; refused in production).

## 3. Run the tests

```powershell
cd tech-radar\backend
.\.venv\Scripts\Activate.ps1
pytest -q                                 # uses a temporary SQLite file, needs nothing else
```

Against real PostgreSQL (recommended before a release). **The tests drop all tables in that database**, so it must be a throw-away one; the suite refuses any name that does not end in `_test`:

```powershell
docker compose -f ..\docker-compose.yml exec db psql -U techradar -c "CREATE DATABASE techradar_test"
$env:TEST_DATABASE_URL = "postgresql+psycopg://techradar:techradar@localhost:5432/techradar_test"
pytest -q
```

## 4. Try the main flow (development mode)

Development auth: send `X-Dev-User: <email>` (and optionally `X-Dev-Role: Admin|Employee`). Seeded users: `admin@neuleap.ai`, `reviewer@neuleap.ai` (a second Admin, because nobody may review their own artifact), `employee@neuleap.ai`.

```powershell
$a = @{ "X-Dev-User" = "admin@neuleap.ai" }
# 1. register a feed (private/internal addresses are refused) and start discovery
Invoke-RestMethod http://localhost:8000/api/v1/sources -Method Post -Headers $a -ContentType "application/json" `
  -Body '{"name":"Hugging Face Blog","url":"https://huggingface.co/blog/feed.xml"}'
$s = Invoke-RestMethod http://localhost:8000/api/v1/discovery/sessions -Method Post -Headers $a
# 2. watch progress, then look at what was published
Invoke-RestMethod "http://localhost:8000/api/v1/admin/agent-runs/$($s.agent_run_id)/events" -Headers $a
Invoke-RestMethod "http://localhost:8000/api/v1/topics" -Headers $a
# 3. topics that need an Admin (no category, or a possible duplicate) wait in pending_review; approve one
Invoke-RestMethod "http://localhost:8000/api/v1/topics?status=pending_review" -Headers $a
Invoke-RestMethod "http://localhost:8000/api/v1/topics/<id>/approve" -Method Post -Headers $a -ContentType "application/json" -Body '{}'
```

Note: the mock LLM (`LLM_PROVIDER=mock`) scores by keyword matching. For real summaries set `LLM_PROVIDER=openai_compatible` plus `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`.

## 5. Production notes

* `ENVIRONMENT` defaults to `production`. The app **refuses to start** in production with dev auth, mock providers, eager Celery, or without `ENTRA_TENANT_ID`/`ENTRA_CLIENT_ID`.
* Set `AUTH_MODE=entra`, `ALLOW_DEV_AUTH=false`, a strong `POSTGRES_PASSWORD`, `CORS_ORIGINS` (your front end URL), and keep secrets out of git (`.env` is git-ignored).
* Put the API behind HTTPS and a reverse proxy that enforces a request-size limit (the API rejects declared sizes above `MAX_UPLOAD_BYTES`, but chunked uploads need the proxy's limit too).
* Share `STORAGE_DIR` between the API and worker (the compose file uses a volume); for several machines replace `app/storage/local.py` with blob storage.
* Run exactly one `beat`. Any number of workers is safe: jobs are idempotent.

## 6. What is verified, and what is not

| Verified | How |
|---|---|
| 163 automated tests pass | on Python 3.11 and 3.13, with SQLite **and** PostgreSQL 16 |
| Alembic: upgrade → no drift (`alembic check`) → downgrade → upgrade | on PostgreSQL 16 |
| A real Celery worker consumed a task from a real Redis | manual smoke test (artifact scan), `--pool=solo` |
| The API served requests under uvicorn on PostgreSQL | manual smoke test |
| `docker compose config` accepts `docker-compose.yml` | validated; **the images were not built or started** (no Docker daemon was available where this was developed) |

| NOT verified | Why / what to do |
|---|---|
| Microsoft Entra sign-in | tested only with locally generated keys; try it against your tenant before relying on it |
| Graph (directory, mail, SharePoint), Teams webhook | tested only with mocked HTTP; see `docs/integrations.md` for permissions |
| Buddy | no real implementation (interface + mock only) |
| Malware scanning | **there is no antivirus engine.** Scans look for secrets, client names, executables and archive tricks; reports say `antivirus: not_configured`. Plug a ClamAV (or similar) `VirusScanner` in `app/security/uploads.py` |
| The OpenAI-compatible LLM client | tested only against a mocked endpoint |
| Web search | no real provider implemented (`none`/`mock`) |
| Load / concurrency under real traffic | not tested |
| The PowerShell commands above | written for Windows but only the Linux equivalents were run; tell me if any line fails on your machine |

## 7. Front end

`frontend/` is the static v2 front end built earlier from the test plan. It keeps its data in the browser and **does not call this API yet**. Known differences to resolve when wiring it up:

* Custom topics: the front end and the backend now agree. A suggested topic is published as soon as its source is verified and it passes the guardrails; with no matching category, or a possible duplicate, it waits for an Admin (`pending_review`).
* Roles: there are two roles now, Employee and Admin. The old Moderator role was merged into Admin (an Entra `TechRadar.Moderator` assignment now gives Admin access; stored Moderators become Admins in migration `0002`).
* Removed on purpose to match the front end: the relevance score and minimum, source pause (`enabled`). Existing databases: run `alembic upgrade head` (migration `0002`; it drops those columns, which cannot be undone for the stored values).
* Example feed sources are no longer seeded by default, because sources are live as soon as they exist. Use `python -m app.seed --example-sources` if you want them.
* Sign-in: use the dev header locally; in production the front end must acquire an Entra access token (MSAL) and send it as a Bearer token.

## 8. Remaining tasks

* Wire the front end to the API (and add MSAL sign-in).
* Real-tenant verification of Entra, Graph and Teams; implement Buddy once its API is known.
* Antivirus integration; blob storage for multi-node deployments.
* More feed kinds (only RSS/Atom `feed` sources exist); a real web-search provider.
* Rate limiting (do it at the reverse proxy or add a middleware), and a data-retention policy for `agent_events` / `audit_logs`.
* Build and run the Docker images in CI.
