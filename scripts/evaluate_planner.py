from __future__ import annotations

import csv
import json
import statistics
import sys
import time
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contour.models import SprintPlanInput
from contour.orchestrator import dry_run_plan_handoff, plan_sprint
from contour.services.llm import LLMService


class EvalJiraClient:
    def __init__(self):
        self.base_url = "https://example.atlassian.net"

    def get(self, path: str, **params):
        if path.endswith("/issuetypes"):
            return {
                "issueTypes": [
                    {"id": "10000", "name": "Epic"},
                    {"id": "10001", "name": "Story"},
                    {"id": "10002", "name": "Task"},
                ]
            }
        if path.endswith("/issuetypes/10000"):
            return {
                "fields": {
                    "summary": {"required": True, "name": "Summary"},
                    "customfield_10011": {"required": True, "name": "Epic Name"},
                    "description": {"required": True, "name": "Description"},
                    "labels": {"required": False, "name": "Labels"},
                    "priority": {"required": False, "name": "Priority"},
                    "reporter": {"required": False, "name": "Reporter"},
                }
            }
        if path.endswith("/issuetypes/10001") or path.endswith("/issuetypes/10002"):
            return {
                "fields": {
                    "summary": {"required": True, "name": "Summary"},
                    "description": {"required": True, "name": "Description"},
                    "labels": {"required": False, "name": "Labels"},
                    "priority": {"required": False, "name": "Priority"},
                    "assignee": {"required": False, "name": "Assignee"},
                    "parent": {"required": False, "name": "Parent"},
                    "customfield_10016": {"required": False, "name": "Story point estimate"},
                    "reporter": {"required": False, "name": "Reporter"},
                }
            }
        if path == "/rest/api/3/field":
            return [
                {"id": "summary", "name": "Summary", "schema": {"type": "string"}},
                {"id": "customfield_10011", "name": "Epic Name", "schema": {"type": "string"}},
                {"id": "description", "name": "Description", "schema": {"type": "string"}},
                {"id": "labels", "name": "Labels", "schema": {"type": "array"}},
                {"id": "priority", "name": "Priority", "schema": {"type": "priority"}},
                {"id": "reporter", "name": "Reporter", "schema": {"type": "user"}},
                {"id": "assignee", "name": "Assignee", "schema": {"type": "user"}},
                {"id": "parent", "name": "Parent", "schema": {"type": "issuelink"}},
                {"id": "customfield_10016", "name": "Story point estimate", "schema": {"type": "number"}},
            ]
        if path == "/rest/api/3/myself":
            return {"accountId": "acct-system"}
        raise ValueError(f"Unsupported Jira metadata path {path}")

    def post(self, path: str, payload: dict):
        raise AssertionError("Evaluation dry-runs should not create Jira issues")


def main() -> None:
    scenarios_path = ROOT / "data" / "eval" / "sprint_scenarios.json"
    artifacts_dir = ROOT / "artifacts" / "eval"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    scenarios = json.loads(scenarios_path.read_text())
    results: list[dict] = []
    latencies: list[float] = []
    dry_run_successes = 0
    schema_valid_count = 0
    expectation_successes = 0
    capacity_violations = 0
    malformed_payloads = 0
    valid_owner_assignments = 0
    assigned_items = 0
    missing_acceptance = 0
    total_plan_items = 0

    jira_client = EvalJiraClient()
    llm_service = LLMService(prefer_llm=False)
    for scenario in scenarios:
        start = time.perf_counter()
        try:
            request = SprintPlanInput.model_validate(scenario)
        except ValidationError as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            latencies.append(latency_ms)
            results.append(
                {
                    "scenario": scenario["sprint_name"],
                    "sprint_goal": scenario["sprint_goal"],
                    "latency_ms": latency_ms,
                    "validation_errors": [
                        {"code": "input_validation_error", "message": error["msg"], "field": ".".join(str(part) for part in error["loc"])}
                        for error in exc.errors()
                    ],
                    "validation_warnings": [],
                    "dry_run_safe_to_execute": False,
                    "estimated_jira_objects": 0,
                    "metrics": {},
                    "expected_constraints": scenario.get("expected_constraints"),
                    "expectation_failures": []
                    if scenario.get("expected_constraints", {}).get("allow_malformed_input")
                    else ["input failed schema validation"],
                }
            )
            if scenario.get("expected_constraints", {}).get("allow_malformed_input"):
                expectation_successes += 1
            continue

        plan = plan_sprint(request, llm_service=llm_service)
        schema_valid_count += 1
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        latencies.append(latency_ms)

        dry_run = dry_run_plan_handoff(
            project_key="CTR",
            plan=plan,
            jira_client=jira_client,
            engineers=request.engineer_profiles,
            team_capacity=request.team_capacity,
            accept_warnings=True,
        )

        validation = plan.validation_result
        expectation_failures = _expectation_failures(request, validation, plan)
        if not expectation_failures:
            expectation_successes += 1

        if validation and any(error.code == "total_points_exceed_capacity" for error in validation.errors):
            capacity_violations += 1
        if dry_run.validation_errors:
            malformed_payloads += len(
                [error for error in dry_run.validation_errors if error.code == "malformed_jira_payload"]
            )
        if dry_run.safe_to_execute:
            dry_run_successes += 1

        total_plan_items += len(plan.plan_items)
        for item in plan.plan_items:
            if item.recommended_assignee:
                assigned_items += 1
                matching_engineer = next(
                    (engineer for engineer in request.engineer_profiles if engineer.name == item.recommended_assignee),
                    None,
                )
                if matching_engineer and (
                    not item.required_skills
                    or set(skill.lower() for skill in item.required_skills)
                    & set(skill.lower() for skill in matching_engineer.skills)
                ):
                    valid_owner_assignments += 1
            if not item.acceptance_criteria:
                missing_acceptance += 1

        results.append(
            {
                "scenario": scenario["sprint_name"],
                "sprint_goal": scenario["sprint_goal"],
                "latency_ms": latency_ms,
                "validation_errors": [error.model_dump() for error in validation.errors] if validation else [],
                "validation_warnings": [warning.model_dump() for warning in validation.warnings] if validation else [],
                "dry_run_safe_to_execute": dry_run.safe_to_execute,
                "estimated_jira_objects": dry_run.estimated_jira_objects,
                "metrics": validation.metrics.model_dump() if validation else {},
                "expected_constraints": request.expected_constraints.model_dump()
                if request.expected_constraints
                else None,
                "expectation_failures": expectation_failures,
            }
        )

    scenario_count = len(scenarios)
    summary = {
        "scenario_count": scenario_count,
        "schema_valid_output_rate": round(schema_valid_count / scenario_count, 4),
        "expectation_satisfaction_rate": round(expectation_successes / scenario_count, 4),
        "capacity_constraint_violation_rate": round(capacity_violations / scenario_count, 4),
        "malformed_jira_payload_rate": round(malformed_payloads / max(scenario_count, 1), 4),
        "owner_assignment_validity_rate": round(valid_owner_assignments / max(assigned_items, 1), 4),
        "missing_acceptance_criteria_rate": round(missing_acceptance / max(total_plan_items, 1), 4),
        "jira_dry_run_success_rate": round(dry_run_successes / scenario_count, 4),
        "mean_planning_latency_ms": round(statistics.mean(latencies), 2),
        "p95_planning_latency_ms": round(_percentile(latencies, 95), 2),
    }

    results_payload = {
        "summary": summary,
        "results": results,
    }
    (artifacts_dir / "planner_eval_results.json").write_text(json.dumps(results_payload, indent=2))

    with (artifacts_dir / "planner_eval_summary.csv").open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)

    print(json.dumps(summary, indent=2))


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(round((percentile / 100) * (len(ordered) - 1)), 0)
    return ordered[index]


def _expectation_failures(request: SprintPlanInput, validation, plan) -> list[str]:
    expected = request.expected_constraints
    if expected is None:
        return []

    failures: list[str] = []
    errors = validation.errors if validation else []
    warnings = validation.warnings if validation else []
    error_codes = {error.code for error in errors}
    warning_codes = {warning.code for warning in warnings}

    if expected.should_fit_capacity is True and "total_points_exceed_capacity" in error_codes:
        failures.append("expected plan to fit capacity, but total points exceed available capacity")
    if expected.should_fit_capacity is False and "total_points_exceed_capacity" not in error_codes:
        failures.append("expected a capacity violation, but none was reported")

    if not expected.allow_missing_acceptance_criteria and "missing_acceptance_criteria" in warning_codes:
        failures.append("missing acceptance criteria were not allowed")

    skill_gap_statuses = {"assigned_with_skill_gap", "unassigned_skill_gap"}
    has_skill_gap = "owner_skill_gap" in warning_codes or any(
        item.assignment_status in skill_gap_statuses for item in plan.plan_items
    )
    if has_skill_gap and not expected.allow_skill_gaps:
        failures.append("skill gaps were not allowed")

    return failures


if __name__ == "__main__":
    main()
