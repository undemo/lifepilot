# LifePilot Submission

This `lifepilot/` directory is the clean online submission package for the LifePilot hackathon demo.

## Scope

- Main backend: `backend/app`, FastAPI APIs under `/api/v1`.
- Main frontend: `frontend/app`, `frontend/components`, `frontend/lib`, and `frontend/types`.
- Stable mock data: `backend/data/fixtures` plus the curated sidecar JSON files in `backend/data`.
- Runtime state is intentionally excluded. `backend/data/runtime/` is created locally when the app or tests run.
- External LLM and AMap calls are disabled by default for review. The demo works through deterministic rules and mock digital-twin data.

## Run

```bash
bash start.sh
```

The script binds the backend to `0.0.0.0:8010` and the frontend to `0.0.0.0:3000` by default, so a server deployment can be opened at `http://<server-ip>:3000`. Set `BACKEND_HOST=127.0.0.1 FRONTEND_HOST=127.0.0.1` if you need local-only access.

## Verify

```bash
bash scripts/verify_submission.sh
```

The verifier runs contract scanning, mock data validation, backend P0 regression, frontend lint/typecheck, and npm audit.

Before zipping or uploading the directory, run:

```bash
bash scripts/check_submission_clean.sh
```

This catches local dependencies, build output, runtime state, caches, logs, and historical reports that should not be submitted.

## Latest Local Verification

- Backend P0 runner: passed.
- Frontend `npm run verify`: passed.
- Frontend `npm audit`: 0 vulnerabilities after upgrading Next to 15.5.19 and pinning PostCSS via npm overrides.
- Contract and mock-data checks are included in `scripts/verify_submission.sh` and should be rerun after any later edits.
