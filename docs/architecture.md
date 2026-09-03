# Architecture

The target design for the deployed application, agreed before implementation.
Sprint 0 prepared the library for it; Sprints 1-4 build it.

## What the product does

Two jobs, matching the two moments a team needs help:

1. **Before launch** - how many users and how many days are needed to detect a
   lift worth having?
2. **After launch** - is the result real, is the data trustworthy, and what
   should we do about it?

Everything in the design serves one of those two. Anything that serves neither
is out of scope.

## Shape

```
Browser ──HTTPS──> Streamlit  (Cloud Run service: ab-ui)
                        │  httpx, JSON over HTTP
                        ▼
                   FastAPI   (Cloud Run service: ab-api)
                        │  in-process import
                        ▼
                   abtest    (the library in src/)
```

Two services rather than one, because they fail and scale differently: the UI
holds websocket sessions and is mostly idle; the API does bounded CPU work per
request. Splitting them also keeps the statistics reachable by anything other
than a browser - a notebook, a scheduled job, a future CLI client.

**Stateless in v1.** No database. The data arrives in the request, the result
comes back in the response, and the report is returned as bytes for download.
Persistence is deferred until there is a user-facing reason for it (saved
experiments, a program-level view), which keeps the deployment inside a free
tier with no storage to manage or leak.

## Backend: FastAPI

| Method | Path | Purpose |
|---|---|---|
| GET | `/health`, `/ready` | Liveness and readiness for the platform |
| GET | `/api/v1/datasets` | Bundled demo datasets |
| POST | `/api/v1/data/inspect` | Upload → columns, dtypes, row count, candidate unit/variant columns |
| POST | `/api/v1/experiments/validate` | Data contract and trust checks only |
| POST | `/api/v1/experiments/analyze` | Full analysis → results JSON |
| POST | `/api/v1/experiments/report` | Same input → self-contained HTML report |
| POST | `/api/v1/power/sample-size` | Baseline and MDE → users per arm, days at a given traffic rate |
| POST | `/api/v1/power/mde` | Sample size → smallest detectable effect |
| POST | `/api/v1/power/curve` | Power curve points |
| POST | `/api/v1/sequential/boundaries` | Interim looks → alpha-spending boundaries |
| GET | `/docs` | OpenAPI, generated |

Cross-cutting concerns:

- **Schemas.** Pydantic v2 models at the boundary, mapping onto the library's
  dataclasses. The library keeps no HTTP knowledge.
- **Errors.** The exception hierarchy added in Sprint 0 maps directly onto
  status codes: `ConfigurationError` and `DataValidationError` → 422,
  `InsufficientDataError` → 409, oversized upload → 413, anything else → 500
  with a request id and no stack trace in the body.
- **Limits.** `MAX_UPLOAD_MB` and `MAX_ROWS` from the environment, enforced
  before parsing. Cloud Run caps request bodies at roughly 32 MiB, so uploads
  are capped below that and rejected cleanly rather than truncated.
- **Logging.** `abtest.log.configure_logging` with `LOG_FORMAT=json` in the
  container, a request id on every line.

## Frontend: Streamlit

A thin client. It renders and collects input; it computes nothing.

1. **Overview** - the Cookie Cats case as a live demo: decision, headline
   finding, what it is worth.
2. **Analyze** - upload → column mapping (driven by `/data/inspect`) → metric
   definition → results, charts, downloadable report.
3. **Plan** - sample size, MDE and duration, framed in traffic and days.
4. **Peeking** - sequential boundaries against a fixed threshold.
5. **Methodology** - what the tool does, and what it will not do.

Charts are rendered client-side from the API's JSON so they stay interactive.
The matplotlib figures in `abtest.reporting.plots` remain the server-side path
for the downloadable report, where a static image is the right artefact.

## Deployment: GCP Cloud Run

Chosen over Azure for this stack:

| | Cloud Run | Azure |
|---|---|---|
| Two containers, scale to zero | One always-free monthly grant covers both; idle costs nothing | Container Apps is comparable; App Service F1 is too constrained for two containers |
| Registry | Artifact Registry has a small always-free allowance | Container Registry Basic is paid - the main cost trap |
| Websockets | Supported with session affinity | Supported |
| Deploy | `gcloud run deploy --source .` | More moving parts |

Azure's advantage is Cosmos DB's free tier, which is irrelevant while v1 holds
no state.

**Cost controls, applied at deploy time:**

- Slim images and a registry cleanup policy keeping two tags per service.
- Explicit `--max-instances`, `--memory` and `--concurrency` so a runaway
  request cannot consume the monthly grant.
- A budget alert at $1.
- Free-tier limits re-checked against current pricing pages before deploying;
  the figures above are structural, not quoted.

Both clouds require a billing account with a card even for $0 usage. If that is
not acceptable, the same containers run on Streamlit Community Cloud plus
Hugging Face Spaces with no card and no code changes.

## What Sprint 0 changed for this

- `src/` layout, so the deployed artefact is the installed package.
- Typed exceptions, so the HTTP layer maps failures without parsing messages.
- Structured logging with env-driven configuration, so a container emits JSON.
- Per-variant caching and vectorised power curves, because both run per request.
- Calibration tests, so a deployed answer is one the team can defend.
