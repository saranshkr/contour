# Contour

Contour is an AI-assisted sprint planning copilot for engineering teams. It accepts structured backlog and team inputs, recommends sprint scope and ownership, surfaces planning risks, and lets a human approve the draft before handing the final plan off to Jira as a single Epic.

## MVP flow

1. Enter sprint goal, backlog items, and team roster in the Next.js planner workspace.
2. Generate a draft sprint plan with selected work, assignee recommendations, capacity usage, and risks.
3. Review and approve the plan.
4. Create one Jira Epic that captures the approved sprint plan.

## Project structure

- `src/contour/models.py` defines the intake, enrichment, risk, and sprint plan contracts.
- `src/contour/services/llm.py` handles planning enrichment and plan proposal generation, with a deterministic fallback when an OpenAI key is unavailable.
- `src/contour/orchestrator.py` exposes `plan_sprint`, `approve_plan`, and `create_plan_epic`.
- `src/contour/api/main.py` provides the FastAPI layer used by the web UI.
- `src/contour/services/field_meta.py` and `src/contour/services/epic_handler.py` provide the Jira metadata and creation layer used for the final handoff.
- `apps/web` contains the Next.js + Tailwind planner workspace.

## Running locally

```bash
pip install -e .
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

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

```bash
cd apps/web
npm test
npm run build
```

For the Playwright happy-path test, install a browser once first:

```bash
cd apps/web
npx playwright install chromium
npm run test:e2e
```

## Notes

- The web UI replaces the old Streamlit MVP and uses structured repeatable forms for backlog items and team members.
- The frontend calls the Python API directly via `NEXT_PUBLIC_API_BASE_URL`.
- Approval is required before Jira creation is allowed.
- The Jira output is intentionally a single Epic that summarizes the approved sprint plan.
