# Contour

Contour is an AI-assisted sprint planning copilot for engineering teams. It accepts structured backlog and team inputs, recommends sprint scope and ownership, surfaces planning risks, and lets a human approve the draft before handing the final plan off to Jira as a single Epic.

## MVP flow

1. Enter sprint goal, backlog items, and team roster in the Next.js planner workspace.
2. Generate a draft sprint plan with selected work, assignee recommendations, capacity usage, and risks.
3. Review and approve the plan.
4. Create one Jira Epic that captures the approved sprint plan.

## Project structure

- `src/contour/models.py` defines the intake, enrichment, risk, and sprint plan contracts.
- `src/contour/services/constraint_validator.py` centralizes structured plan guardrails and capacity metrics.
- `src/contour/services/llm.py` handles planning enrichment and plan proposal generation, with a deterministic fallback when an OpenAI key is unavailable.
- `src/contour/orchestrator.py` exposes `plan_sprint`, `approve_plan`, Jira dry-run previews, and idempotent Jira handoff.
- `src/contour/services/jira_sync_store.py` persists Jira sync state and idempotency keys in SQLite.
- `src/contour/api/main.py` provides the FastAPI layer used by the web UI.
- `src/contour/services/field_meta.py` and `src/contour/services/epic_handler.py` provide the Jira metadata and creation layer used for the final handoff.
- `scripts/evaluate_planner.py` runs the synthetic evaluation suite and writes reliability artifacts.
- `apps/web` contains the Next.js + Tailwind planner workspace.

## Running locally

Prefer installing from `pyproject.toml`:

```bash
pip install -e .
uvicorn contour.api.main:app --reload --app-dir src
```

If you need a plain requirements-based install instead, use:

```bash
pip install -r requirements.txt
uvicorn contour.api.main:app --reload --app-dir src
```

In a second terminal:

```bash
cd apps/web
npm install
npm run dev
```

Set the following environment variables for Jira handoff and live LLM calls:

- `OPENAI_API_KEY`
- `OPENAI_MODEL` (optional)
- `OPENAI_REASONING_EFFORT` (optional, recommended for GPT-5-family models)
- `OPENAI_TEXT_VERBOSITY` (optional)
- `JIRA_BASE_URL`
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`

Contour now uses the OpenAI Responses API automatically for GPT-5-family models and keeps the existing LangChain chat path for older models. A good default for this repo is `OPENAI_MODEL=gpt-5.4-mini` with `OPENAI_REASONING_EFFORT=low`.

## Testing

Backend:

```bash
pytest
```

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

Frontend:

```bash
cd apps/web
npm test
npm run build
```

End-to-end:

```bash
cd apps/web
npx playwright install
npx playwright test
```

## Reliability, Evaluation, and Safe Jira Handoff

SprintPilot now includes a production-aware planning safety layer on top of the original LLM-to-Jira flow.

- Planner evaluation harness: `scripts/evaluate_planner.py` runs 20 synthetic sprint scenarios from `data/eval/sprint_scenarios.json` and writes structured outputs to `artifacts/eval/planner_eval_results.json` and `artifacts/eval/planner_eval_summary.csv`.
- Validation guardrails: `constraint_validator.py` checks overloaded engineers, invalid point buckets, missing titles or descriptions, missing acceptance criteria, unsupported task types, owner-skill mismatches, duplicate backlog item IDs, invalid priority or status values, total points over capacity, and malformed Jira previews.
- Dry-run behavior: `POST /api/v1/jira/dry-run` builds the Epic and child issue payload previews, returns validation errors and warnings, estimates the number of Jira objects that would be created, and marks whether execution is safe.
- Idempotent Jira handoff: every approved plan gets a deterministic idempotency key, Jira sync state is persisted in SQLite, retries reuse existing Epic or child issue keys, and sync status is tracked with `NOT_STARTED`, `DRY_RUN_PASSED`, `SYNC_IN_PROGRESS`, `SYNC_SUCCEEDED`, `SYNC_FAILED`, and `PARTIAL_FAILURE`.
- Typed contracts: backend responses are defined in Pydantic models and mirrored in frontend Zod schemas for sprint input, sprint plans, validation results, dry-run responses, and Jira sync state.
- UI workflow: users can generate a plan, inspect validation errors and warnings, review capacity utilization, run a Jira dry-run, approve only when validation errors are resolved, and create Jira issues only after dry-run passes and warnings are explicitly accepted.

Run the reliability suite and tests with:

```bash
python scripts/evaluate_planner.py
```

If your environment exposes `python3` instead of `python`, use `python3 scripts/evaluate_planner.py`.

```bash
pytest
```

```bash
cd apps/web
npm test
```

```bash
cd apps/web
npx playwright test
```

## Notes

- The web UI replaces the old Streamlit MVP and uses structured repeatable forms for backlog items and team members.
- The frontend calls the Python API directly via `NEXT_PUBLIC_API_BASE_URL`.
- Approval is blocked when validation errors are present, and Jira creation is blocked until dry-run passes.
- The Jira output is intentionally a single Epic that summarizes the approved sprint plan.
