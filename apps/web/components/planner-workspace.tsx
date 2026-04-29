"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { z } from "zod";

import { plannerApi, PlannerApi } from "@/lib/api";
import { SurfaceSection } from "@/components/surface-section";
import {
  createEmptySprintRequest,
  createEmptyTask,
  EmployeeRecord,
  EngineerProfile,
  JiraDryRunResponse,
  JiraHandoffResponse,
  PlanItem,
  SprintPlan,
  SprintRequest,
  SprintPlanValidationResult,
  sprintRequestSchema,
} from "@/lib/schemas";

type BannerTone = "success" | "error" | "info";
type PendingAction = "sample" | "generate" | "approve" | "dry-run" | "handoff" | null;

type BannerState = {
  tone: BannerTone;
  message: string;
};

const inputClassName = "field-shell w-full";
const labelClassName =
  "mb-2 block text-xs font-semibold uppercase tracking-[0.28em] text-slate-300/75";
const STORY_POINT_OPTIONS = [1, 2, 3, 5, 8];

export function PlannerWorkspace({
  apiClient = plannerApi,
}: {
  apiClient?: PlannerApi;
}) {
  const [request, setRequest] = useState<SprintRequest>(createEmptySprintRequest());
  const [employees, setEmployees] = useState<EmployeeRecord[]>([]);
  const [projectKey, setProjectKey] = useState("CTR");
  const [plan, setPlan] = useState<SprintPlan | null>(null);
  const [dryRun, setDryRun] = useState<JiraDryRunResponse | null>(null);
  const [handoffResult, setHandoffResult] = useState<JiraHandoffResponse | null>(null);
  const [warningsAccepted, setWarningsAccepted] = useState(false);
  const [banner, setBanner] = useState<BannerState | null>(null);
  const [requestErrors, setRequestErrors] = useState<string[]>([]);
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadEmployees() {
      try {
        const roster = await apiClient.loadEmployees();
        if (!cancelled) {
          setEmployees(roster);
        }
      } catch (error) {
        if (!cancelled) {
          setBanner({ tone: "error", message: getErrorMessage(error) });
        }
      }
    }

    void loadEmployees();
    return () => {
      cancelled = true;
    };
  }, [apiClient]);

  const validation = plan?.validation_result ?? null;
  const planningRoster = request.engineer_profiles.length > 0 ? request.engineer_profiles : employees;
  const hasValidationErrors = Boolean(validation && validation.errors.length > 0);
  const hasValidationWarnings = Boolean(validation && validation.warnings.length > 0);
  const hasDryRunWarnings = Boolean(dryRun && dryRun.validation_warnings.length > 0);
  const hasWarningsNeedingAcceptance = hasValidationWarnings || hasDryRunWarnings;
  const dryRunPassed = dryRun?.safe_to_execute ?? false;
  const canApprove = Boolean(plan && !hasValidationErrors && pendingAction === null);
  const canRunDryRun = Boolean(plan && (!hasWarningsNeedingAcceptance || warningsAccepted) && pendingAction === null);
  const canCreateJira = Boolean(
    plan &&
      plan.approval_state === "approved" &&
      dryRunPassed &&
      (!hasWarningsNeedingAcceptance || warningsAccepted) &&
      pendingAction === null
  );

  const syncStatusLabel = useMemo(() => {
    if (handoffResult?.sync_state?.status) {
      return handoffResult.sync_state.status;
    }
    if (dryRun?.sync_state?.status) {
      return dryRun.sync_state.status;
    }
    return "NOT_STARTED";
  }, [dryRun, handoffResult]);

  async function runAction<T>(
    action: Exclude<PendingAction, null>,
    work: () => Promise<T>
  ) {
    setPendingAction(action);
    try {
      return await work();
    } finally {
      setPendingAction(null);
    }
  }

  function updateRequest(patch: Partial<SprintRequest>) {
    setRequest((current) => ({ ...current, ...patch }));
  }

  function updateTask(index: number, patch: Partial<SprintRequest["tasks"][number]>) {
    setRequest((current) => ({
      ...current,
      tasks: current.tasks.map((task, taskIndex) =>
        taskIndex === index ? { ...task, ...patch } : task
      ),
    }));
  }

  function updateTeamCapacity(patch: Partial<NonNullable<SprintRequest["team_capacity"]>>) {
    setRequest((current) => ({
      ...current,
      team_capacity: {
        available_points: current.team_capacity?.available_points ?? null,
        buffer_points: current.team_capacity?.buffer_points ?? 0,
        ...patch,
      },
    }));
  }

  function updateEngineerProfile(index: number, patch: Partial<EngineerProfile>) {
    setRequest((current) => {
      const roster = current.engineer_profiles.length > 0 ? current.engineer_profiles : employees;
      return {
        ...current,
        engineer_profiles: roster.map((engineer, engineerIndex) =>
          engineerIndex === index ? { ...engineer, ...patch } : engineer
        ),
      };
    });
  }

  function addEngineerProfile() {
    setRequest((current) => ({
      ...current,
      engineer_profiles: [
        ...(current.engineer_profiles.length > 0 ? current.engineer_profiles : employees),
        {
          id: `custom-${(current.engineer_profiles.length || employees.length) + 1}`,
          name: "",
          role: "",
          skills: [],
          capacity_points: 0,
          jira_account_id: "",
        },
      ],
    }));
  }

  function resetDerivedState() {
    setPlan(null);
    setDryRun(null);
    setHandoffResult(null);
    setWarningsAccepted(false);
  }

  function invalidatePostEditState() {
    setDryRun(null);
    setHandoffResult(null);
    setWarningsAccepted(false);
  }

  function updatePlanItem(index: number, patch: Partial<PlanItem>) {
    setPlan((current) => {
      if (!current) {
        return current;
      }
      const nextPlan = {
        ...current,
        approval_state: "draft" as const,
        validation_result: null,
        plan_items: current.plan_items.map((item, itemIndex) =>
          itemIndex === index ? { ...item, ...patch } : item
        ),
      };
      return nextPlan;
    });
    invalidatePostEditState();
  }

  function handleAssigneeChange(index: number, employeeId: string) {
    if (!plan) {
      return;
    }
    const item = plan.plan_items[index];
    const employee = planningRoster.find((candidate) => candidate.id === employeeId) ?? null;

    updatePlanItem(index, {
      recommended_assignee: employee?.name ?? null,
      recommended_assignee_account_id: employee?.jira_account_id ?? null,
      assignment_status: previewAssignmentStatus(item, employee),
    });
  }

  async function handleLoadSample() {
    await runAction("sample", async () => {
      try {
        const sampleRequest = await apiClient.loadSampleRequest();
        setRequest(sampleRequest);
        resetDerivedState();
        setRequestErrors([]);
        setBanner({ tone: "success", message: "Loaded sample sprint data." });
      } catch (error) {
        setBanner({ tone: "error", message: getErrorMessage(error) });
      }
    });
  }

  async function handleGeneratePlan() {
    const parsed = sprintRequestSchema.safeParse(request);
    if (!parsed.success) {
      setRequestErrors(formatValidationErrors(parsed.error));
      setBanner({
        tone: "error",
        message: "Please fix the request details before generating a plan.",
      });
      return;
    }

    await runAction("generate", async () => {
      try {
        const draftPlan = await apiClient.generatePlan(parsed.data);
        setPlan(draftPlan);
        setDryRun(null);
        setHandoffResult(null);
        setWarningsAccepted(false);
        setRequestErrors([]);
        setBanner({
          tone: "success",
          message: plan ? "Draft regenerated." : "Draft sprint plan generated.",
        });
      } catch (error) {
        setBanner({ tone: "error", message: getErrorMessage(error) });
      }
    });
  }

  async function handleApprovePlan() {
    if (!plan) {
      return;
    }

    await runAction("approve", async () => {
      try {
        const approvedPlan = await apiClient.approvePlan(plan, request);
        setPlan(approvedPlan);
        setBanner({
          tone: "success",
          message: "Plan approved and ready for Jira handoff.",
        });
      } catch (error) {
        setBanner({ tone: "error", message: getErrorMessage(error) });
      }
    });
  }

  async function handleDryRun() {
    if (!plan) {
      return;
    }

    await runAction("dry-run", async () => {
      try {
        const result = await apiClient.dryRunPlan(projectKey, plan, {
          acceptWarnings: warningsAccepted,
          context: request,
        });
        setDryRun(result);
        setWarningsAccepted((current) => current && result.safe_to_execute);
        setBanner({
          tone: result.safe_to_execute ? "success" : "error",
          message: result.safe_to_execute
            ? "Jira dry-run passed."
            : "Jira dry-run found issues that need attention.",
        });
      } catch (error) {
        setBanner({ tone: "error", message: getErrorMessage(error) });
      }
    });
  }

  async function handleJiraHandoff() {
    if (!plan || plan.approval_state !== "approved") {
      return;
    }

    await runAction("handoff", async () => {
      try {
        const result = await apiClient.handoffPlan(projectKey, plan, {
          acceptWarnings: warningsAccepted,
          context: request,
        });
        setHandoffResult(result);
        setBanner({ tone: "success", message: `Created Jira epic ${result.key}.` });
      } catch (error) {
        setBanner({ tone: "error", message: getErrorMessage(error) });
      }
    });
  }

  return (
    <main className="mx-auto min-h-screen max-w-7xl px-5 py-8 sm:px-8 lg:px-10">
      <div className="mb-8 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl">
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.42em] text-contour-tide/90">
            Sprint Planning Copilot
          </p>
          <h1 className="text-4xl leading-tight text-white sm:text-5xl">
            Turn natural-language tasks into an approval-ready Jira delivery plan.
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-200/80 sm:text-lg">
            Contour normalizes freeform work requests, validates sprint constraints, previews
            Jira payloads, and keeps a human review gate before any Jira creation happens.
          </p>
        </div>

        <div className="surface-panel flex w-full max-w-md flex-col gap-4 rounded-[2rem] p-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.32em] text-slate-300/70">
              Jira Handoff
            </p>
            <p className="mt-2 text-sm text-slate-300/85">
              Dry-run validation and explicit warning acceptance now gate the final Jira sync.
            </p>
          </div>
          <label className="block">
            <span className={labelClassName}>Project Key</span>
            <input
              aria-label="Jira project key"
              className={inputClassName}
              value={projectKey}
              onChange={(event) => setProjectKey(event.target.value.toUpperCase())}
              placeholder="CTR"
            />
          </label>
        </div>
      </div>

      {banner ? <StatusBanner banner={banner} /> : null}

<<<<<<< Updated upstream
      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <SurfaceSection
          eyebrow="Intake"
          title="Shape the sprint request"
          description="Use structured backlog and team forms instead of raw JSON, then load sample data or generate the draft."
        >
          <div className="flex flex-wrap gap-3">
            <ActionButton
              label={pendingAction === "sample" ? "Loading Sample..." : "Load Sample Data"}
              onClick={handleLoadSample}
              disabled={pendingAction !== null}
              tone="secondary"
            />
            <ActionButton
              label={pendingAction === "generate" ? "Generating..." : generateLabel}
              onClick={handleGeneratePlan}
              disabled={pendingAction !== null}
              tone="primary"
            />
          </div>

          {validationErrors.length > 0 ? (
            <div className="mt-5 rounded-3xl border border-red-300/20 bg-red-400/10 p-4">
              <p className="text-sm font-semibold text-red-100">Request validation</p>
              <ul className="mt-3 space-y-2 text-sm text-red-50/90">
                {validationErrors.map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="mt-6 grid gap-5 lg:grid-cols-2">
            <label className="block">
              <span className={labelClassName}>Sprint Name</span>
              <input
                aria-label="Sprint name"
                className={inputClassName}
                value={request.sprint_name}
                onChange={(event) => updateRequest({ sprint_name: event.target.value })}
                placeholder="Sprint 18"
              />
            </label>
            <label className="block">
              <span className={labelClassName}>Sprint Goal</span>
              <textarea
                aria-label="Sprint goal"
                className={`${inputClassName} min-h-28`}
                value={request.goal}
                onChange={(event) => updateRequest({ goal: event.target.value })}
                placeholder="Ship a reliable planning and Jira handoff flow."
              />
            </label>
          </div>

          <div className="mt-8">
            <div className="mb-4 flex items-center justify-between gap-4">
              <div>
                <h2 className="text-2xl text-white">Backlog Items</h2>
                <p className="mt-1 text-sm text-slate-300/75">
                  Add one natural-language task per card. Keep each task focused enough for Jira ticket generation.
                </p>
              </div>
=======
      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <div className="grid gap-6">
          <SectionPanel
            eyebrow="Intake"
            title="Shape the sprint request"
            description="Enter the sprint goal and freeform tasks. Contour uses the employee roster as planning context and validates the draft before Jira handoff."
          >
            <div className="flex flex-wrap gap-3">
>>>>>>> Stashed changes
              <ActionButton
                label="Add Task"
                onClick={() => updateRequest({ tasks: [...request.tasks, createEmptyTask(request.tasks.length + 1)] })}
                disabled={pendingAction !== null}
                tone="secondary"
              />
<<<<<<< Updated upstream
            </div>

            <div className="space-y-4">
              {request.tasks.map((task, index) => (
                <div key={`task-${index}`} className="rounded-[1.75rem] border border-white/10 bg-white/5 p-5">
                  <div className="mb-4 flex items-center justify-between gap-4">
                    <p className="text-sm font-semibold uppercase tracking-[0.28em] text-slate-300/70">
                      Task {index + 1}
                    </p>
                    {request.tasks.length > 1 ? (
                      <button
                        className="text-sm font-semibold text-red-200 transition hover:text-red-100"
                        onClick={() =>
                          updateRequest({
                            tasks: request.tasks.filter((_, taskIndex) => taskIndex !== index),
                          })
                        }
                        type="button"
                      >
                        Remove
                      </button>
                    ) : null}
=======
              <ActionButton
                label={
                  pendingAction === "generate"
                    ? "Generating..."
                    : plan
                      ? "Regenerate Draft"
                      : "Generate Draft Plan"
                }
                onClick={handleGeneratePlan}
                disabled={pendingAction !== null}
                tone="primary"
              />
            </div>

            {requestErrors.length > 0 ? (
              <ValidationPanel
                title="Request validation"
                tone="error"
                messages={requestErrors.map((message) => ({ code: "request", message }))}
              />
            ) : null}

            <div className="mt-6 grid gap-5 lg:grid-cols-2">
              <Field label="Sprint Name">
                <input
                  aria-label="Sprint name"
                  className={inputClassName}
                  value={request.sprint_name}
                  onChange={(event) => {
                    updateRequest({ sprint_name: event.target.value });
                    resetDerivedState();
                  }}
                  placeholder="Sprint 18"
                />
              </Field>
              <Field label="Sprint Goal">
                <textarea
                  aria-label="Sprint goal"
                  className={`${inputClassName} min-h-28`}
                  value={request.goal}
                  onChange={(event) => {
                    updateRequest({ goal: event.target.value });
                    resetDerivedState();
                  }}
                  placeholder="Ship a reliable planning and Jira handoff flow."
                />
              </Field>
            </div>

            <div className="mt-5 grid gap-5 lg:grid-cols-2">
              <Field label="Available Team Points">
                <input
                  aria-label="Available team points"
                  className={inputClassName}
                  min={0}
                  type="number"
                  value={request.team_capacity?.available_points ?? ""}
                  onChange={(event) => {
                    updateTeamCapacity({
                      available_points: event.target.value === "" ? null : Number.parseInt(event.target.value, 10),
                    });
                    resetDerivedState();
                  }}
                  placeholder="Use roster total"
                />
              </Field>
              <Field label="Capacity Buffer Points">
                <input
                  aria-label="Capacity buffer points"
                  className={inputClassName}
                  min={0}
                  type="number"
                  value={request.team_capacity?.buffer_points ?? 0}
                  onChange={(event) => {
                    updateTeamCapacity({ buffer_points: Number.parseInt(event.target.value || "0", 10) });
                    resetDerivedState();
                  }}
                />
              </Field>
            </div>

            <div className="mt-8">
              <div className="mb-4 flex items-center justify-between gap-4">
                <div>
                  <h2 className="text-2xl text-white">Task List</h2>
                  <p className="mt-1 text-sm text-slate-300/75">
                    Add one natural-language task per card. Acceptance criteria are optional but
                    highlighted when missing.
                  </p>
                </div>
                <ActionButton
                  label="Add Task"
                  onClick={() => {
                    updateRequest({ tasks: [...request.tasks, createEmptyTask()] });
                    resetDerivedState();
                  }}
                  disabled={pendingAction !== null}
                  tone="secondary"
                />
              </div>

              <div className="space-y-4">
                {request.tasks.map((task, index) => (
                  <div key={`task-${index}`} className="rounded-[1.75rem] border border-white/10 bg-white/5 p-5">
                    <div className="mb-4 flex items-center justify-between gap-4">
                      <p className="text-sm font-semibold uppercase tracking-[0.28em] text-slate-300/70">
                        Task {index + 1}
                      </p>
                      {request.tasks.length > 1 ? (
                        <button
                          className="text-sm font-semibold text-red-200 transition hover:text-red-100"
                          onClick={() => {
                            updateRequest({
                              tasks: request.tasks.filter((_, taskIndex) => taskIndex !== index),
                            });
                            resetDerivedState();
                          }}
                          type="button"
                        >
                          Remove
                        </button>
                      ) : null}
                    </div>

                    <div className="grid gap-4 md:grid-cols-[1.4fr_0.6fr]">
                      <Field label="Task Description">
                        <textarea
                          aria-label={`Task ${index + 1} description`}
                          className={`${inputClassName} min-h-32`}
                          value={task.text ?? ""}
                          onChange={(event) => {
                            updateTask(index, { text: event.target.value });
                            resetDerivedState();
                          }}
                          placeholder="Describe the work in natural language."
                        />
                      </Field>
                      <Field label="Owner Hint">
                        <input
                          aria-label={`Task ${index + 1} owner hint`}
                          className={inputClassName}
                          value={task.owner_hint ?? ""}
                          onChange={(event) => {
                            updateTask(index, { owner_hint: emptyToNull(event.target.value) });
                            resetDerivedState();
                          }}
                          placeholder="Optional teammate name"
                        />
                      </Field>
                    </div>
                    <div className="mt-4">
                      <Field label="Acceptance Criteria">
                        <textarea
                          aria-label={`Task ${index + 1} acceptance criteria`}
                          className={`${inputClassName} min-h-24`}
                          value={(task.acceptance_criteria ?? []).join("\n")}
                          onChange={(event) => {
                            updateTask(index, { acceptance_criteria: splitLines(event.target.value) });
                            resetDerivedState();
                          }}
                          placeholder="One acceptance criterion per line."
                        />
                      </Field>
                    </div>
>>>>>>> Stashed changes
                  </div>

<<<<<<< Updated upstream
                  <div className="grid gap-4 md:grid-cols-[1.4fr_0.6fr]">
                    <Field label="Task Description">
                      <textarea
                        aria-label={`Task ${index + 1} description`}
                        className={`${inputClassName} min-h-32`}
                        value={task.text}
                        onChange={(event) => updateTask(index, { text: event.target.value })}
                        placeholder="Describe the work in natural language."
                      />
                    </Field>
                    <Field label="Owner Hint">
                      <input
                        aria-label={`Task ${index + 1} owner hint`}
                        className={inputClassName}
                        value={task.owner_hint ?? ""}
                        onChange={(event) => updateTask(index, { owner_hint: emptyToNull(event.target.value) })}
                        placeholder="Optional teammate name"
                      />
                    </Field>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-8">
            <div className="mb-4">
              <h2 className="text-2xl text-white">Built-in employee roster</h2>
              <p className="mt-1 text-sm text-slate-300/75">
                Contour considers the full employee roster for every planning run and uses the Jira account IDs attached to each employee for assignment.
              </p>
            </div>

            {employees.length > 0 ? (
=======
          <SectionPanel
            eyebrow="Roster"
            title="Planning roster"
            description="Edit the team context used for skill matching, capacity validation, approval, and Jira assignment previews."
          >
            {planningRoster.length > 0 ? (
              <>
                <div className="mb-4 flex flex-wrap gap-3">
                  <ActionButton
                    label="Use Built-In Roster"
                    onClick={() => {
                      updateRequest({ engineer_profiles: employees });
                      resetDerivedState();
                    }}
                    disabled={pendingAction !== null || employees.length === 0}
                    tone="secondary"
                  />
                  <ActionButton
                    label="Add Engineer"
                    onClick={() => {
                      addEngineerProfile();
                      resetDerivedState();
                    }}
                    disabled={pendingAction !== null}
                    tone="secondary"
                  />
                </div>
>>>>>>> Stashed changes
              <div className="grid gap-4 lg:grid-cols-2">
                {planningRoster.map((employee, index) => (
                  <div key={employee.id} className="rounded-[1.75rem] border border-white/10 bg-white/5 p-5">
                    <div className="grid gap-4 sm:grid-cols-[1fr_0.45fr]">
                      <Field label="Name">
                        <input
                          aria-label={`Engineer ${index + 1} name`}
                          className={inputClassName}
                          value={employee.name}
                          onChange={(event) => {
                            updateEngineerProfile(index, { name: event.target.value });
                            resetDerivedState();
                          }}
                        />
                      </Field>
                      <Field label="Capacity">
                        <input
                          aria-label={`Engineer ${index + 1} capacity`}
                          className={inputClassName}
                          min={0}
                          type="number"
                          value={employee.capacity_points}
                          onChange={(event) => {
                            updateEngineerProfile(index, {
                              capacity_points: Number.parseInt(event.target.value || "0", 10),
                            });
                            resetDerivedState();
                          }}
                        />
                      </Field>
                    </div>
                    <div className="mt-4 grid gap-4 sm:grid-cols-2">
                      <Field label="Role">
                        <input
                          aria-label={`Engineer ${index + 1} role`}
                          className={inputClassName}
                          value={employee.role}
                          onChange={(event) => {
                            updateEngineerProfile(index, { role: event.target.value });
                            resetDerivedState();
                          }}
                        />
                      </Field>
                      <Field label="Jira Account ID">
                        <input
                          aria-label={`Engineer ${index + 1} Jira account ID`}
                          className={inputClassName}
                          value={employee.jira_account_id}
                          onChange={(event) => {
                            updateEngineerProfile(index, { jira_account_id: event.target.value });
                            resetDerivedState();
                          }}
                        />
                      </Field>
                    </div>
                    <div className="mt-4">
                      <Field label="Skills">
                        <input
                          aria-label={`Engineer ${index + 1} skills`}
                          className={inputClassName}
                          value={employee.skills.join(", ")}
                          onChange={(event) => {
                            updateEngineerProfile(index, { skills: splitCommaList(event.target.value) });
                            resetDerivedState();
                          }}
                          placeholder="frontend, react, jira"
                        />
                      </Field>
                    </div>
                  </div>
                ))}
              </div>
              </>
            ) : (
              <EmptyState message="Loading the employee roster for assignment guidance." />
            )}
          </div>
        </SurfaceSection>

        <div className="grid gap-6">
          <SurfaceSection
            eyebrow="Draft Review"
            title="Inspect the recommendation"
            description="Planner output stays editable, but validation and dry-run states remain visible so Jira handoff decisions are grounded in guardrails."
          >
            {plan ? (
              <>
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  <MetricTile label="Assigned Points" value={plan.capacity_summary.assigned_points} accent="teal" />
                  <MetricTile label="Unassigned Points" value={plan.capacity_summary.unassigned_points} accent="amber" />
                  <MetricTile label="Total Capacity" value={plan.capacity_summary.total_capacity_points} accent="blue" />
                  <MetricTile
                    label="Capacity Usage"
                    value={`${Math.round((validation?.metrics.capacity_utilization ?? 0) * 100)}%`}
                    accent="blue"
                  />
                </div>

                <div className="mt-6 rounded-[1.75rem] border border-white/10 bg-white/5 p-5">
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.32em] text-slate-300/70">
                        Current State
                      </p>
                      <h3 className="mt-2 text-2xl text-white">{capitalize(plan.approval_state)}</h3>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <StatePill tone={!validation ? "info" : hasValidationErrors ? "error" : "success"}>
                        {!validation ? "Validation pending" : hasValidationErrors ? "Validation failed" : "Validation ready"}
                      </StatePill>
                      <StatePill tone={hasValidationWarnings ? "warning" : "success"}>
                        {hasValidationWarnings ? "Warnings present" : "No warnings"}
                      </StatePill>
                      <StatePill tone={dryRunPassed ? "success" : "info"}>
                        {dryRunPassed ? "Dry-run passed" : "Dry-run pending"}
                      </StatePill>
                      <StatePill tone={syncStatusToTone(syncStatusLabel)}>{syncStatusLabel}</StatePill>
                    </div>
                  </div>
                  <p className="mt-4 text-sm leading-7 text-slate-300/80">{plan.goal}</p>
                </div>

                {validation ? (
                  <div className="mt-6 grid gap-4">
                    {validation.errors.length > 0 ? (
                      <ValidationPanel title="Validation errors" tone="error" messages={validation.errors} />
                    ) : null}
                    {validation.warnings.length > 0 ? (
                      <ValidationPanel title="Validation warnings" tone="warning" messages={validation.warnings} />
                    ) : null}
                  </div>
                ) : null}

                <ReviewBlock title="Planned Jira Tickets">
                  <div className="space-y-4">
                    {plan.plan_items.map((item, index) => (
                      <div key={item.task_id} className="rounded-[1.75rem] border border-white/10 bg-white/5 p-5">
                        <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-300/70">
                              {item.task_id}
                            </p>
                            <h4 className="mt-2 text-xl text-white">{item.title}</h4>
                            <p className="mt-2 text-sm leading-6 text-slate-300/80">{item.task_text}</p>
                          </div>
                          <AssignmentBadge status={item.assignment_status} />
                        </div>

                        <div className="grid gap-4 md:grid-cols-2">
                          <Field label="Jira Summary">
                            <input
                              aria-label={`${item.task_id} summary`}
                              className={inputClassName}
                              value={item.title}
                              onChange={(event) => updatePlanItem(index, { title: event.target.value })}
                            />
                          </Field>
                          <Field label="Issue Type">
                            <select
                              aria-label={`${item.task_id} issue type`}
                              className={inputClassName}
                              value={item.jira_issue_type}
                              onChange={(event) =>
                                updatePlanItem(index, {
                                  jira_issue_type: event.target.value as PlanItem["jira_issue_type"],
                                })
                              }
                            >
                              {["Story", "Task"].map((issueType) => (
                                <option key={issueType} value={issueType}>
                                  {issueType}
                                </option>
                              ))}
                            </select>
                          </Field>
                          <Field label="Priority">
                            <select
                              aria-label={`${item.task_id} priority`}
                              className={inputClassName}
                              value={item.priority}
                              onChange={(event) =>
                                updatePlanItem(index, {
                                  priority: event.target.value as PlanItem["priority"],
                                })
                              }
                            >
                              {["high", "medium", "low"].map((priority) => (
                                <option key={priority} value={priority}>
                                  {capitalize(priority)}
                                </option>
                              ))}
                            </select>
                          </Field>
                          <Field label="Story Points">
                            <select
                              aria-label={`${item.task_id} story points`}
                              className={inputClassName}
                              value={String(item.story_points)}
                              onChange={(event) =>
                                updatePlanItem(index, {
                                  story_points: Number.parseInt(event.target.value, 10),
                                })
                              }
                            >
                              {STORY_POINT_OPTIONS.map((points) => (
                                <option key={points} value={points}>
                                  {points}
                                </option>
                              ))}
                            </select>
                          </Field>
                        </div>

                        <div className="mt-4 grid gap-4 md:grid-cols-[1.1fr_0.9fr]">
                          <Field label="Jira Description">
                            <textarea
                              aria-label={`${item.task_id} description`}
                              className={`${inputClassName} min-h-32`}
                              value={item.description}
                              onChange={(event) => updatePlanItem(index, { description: event.target.value })}
                            />
                          </Field>
                          <Field label="Assignee">
                            <select
                              aria-label={`${item.task_id} assignee`}
                              className={inputClassName}
                              value={
                                planningRoster.find(
                                  (employee) => employee.jira_account_id === item.recommended_assignee_account_id
                                )?.id ?? ""
                              }
                              onChange={(event) => handleAssigneeChange(index, event.target.value)}
                            >
                              <option value="">Unassigned</option>
                              {planningRoster.map((employee) => (
                                <option key={employee.id} value={employee.id}>
                                  {employee.name}
                                </option>
                              ))}
                            </select>
                          </Field>
                        </div>

                        <div className="mt-4">
                          <Field label="Acceptance Criteria">
                            <textarea
                              aria-label={`${item.task_id} acceptance criteria`}
                              className={`${inputClassName} min-h-24`}
                              value={item.acceptance_criteria.join("\n")}
                              onChange={(event) =>
                                updatePlanItem(index, { acceptance_criteria: splitLines(event.target.value) })
                              }
                            />
                          </Field>
                        </div>

                        <div className="mt-4 flex flex-wrap gap-2">
                          {item.required_skills.map((skill) => (
                            <Tag key={`${item.task_id}-${skill}`}>{skill}</Tag>
                          ))}
                        </div>

                        <div className="mt-4 grid gap-4 xl:grid-cols-3">
                          <CopyBlock title="Estimation rationale" body={item.estimation_rationale} />
                          <CopyBlock title="Selection rationale" body={item.selection_rationale} />
                          <CopyBlock title="Assignment rationale" body={item.assignment_rationale} />
                        </div>
                      </div>
                    ))}
                  </div>
                </ReviewBlock>

                <ReviewBlock title="Capacity by Employee">
                  <div className="overflow-hidden rounded-[1.75rem] border border-white/10">
                    <table className="min-w-full divide-y divide-white/10 text-left text-sm text-slate-100">
                      <thead className="bg-white/5 text-xs uppercase tracking-[0.24em] text-slate-300/75">
                        <tr>
                          <th className="px-4 py-3">Employee</th>
                          <th className="px-4 py-3">Assigned</th>
                          <th className="px-4 py-3">Capacity</th>
                          <th className="px-4 py-3">Remaining</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/10 bg-slate-950/25">
                        {plan.capacity_summary.allocations.map((allocation) => (
                          <tr key={allocation.member_name}>
                            <td className="px-4 py-3">{allocation.member_name}</td>
                            <td className="px-4 py-3">{allocation.assigned_points}</td>
                            <td className="px-4 py-3">{allocation.capacity_points}</td>
                            <td className="px-4 py-3">{allocation.remaining_points}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </ReviewBlock>
              </>
            ) : (
              <EmptyState message="Generate a draft to review normalized Jira tickets, validation results, point estimates, ownership, and dry-run readiness." />
            )}
          </SurfaceSection>

          <SurfaceSection
            eyebrow="Approval"
            title="Validate the Jira handoff"
            description="Approval is blocked by validation errors. Jira creation is blocked until dry-run passes, and warnings must be explicitly accepted."
          >
            <div className="flex flex-wrap gap-3">
              <ActionButton
                label={pendingAction === "dry-run" ? "Running Dry-Run..." : "Run Jira Dry-Run"}
                onClick={handleDryRun}
                disabled={!canRunDryRun}
                tone="secondary"
              />
              <ActionButton
                label={pendingAction === "approve" ? "Approving..." : "Approve Plan"}
                onClick={handleApprovePlan}
                disabled={!canApprove || (plan?.approval_state === "approved" && pendingAction === null)}
                tone="primary"
              />
              <ActionButton
                label={pendingAction === "handoff" ? "Creating Jira Tickets..." : "Create Jira Epic + Tickets"}
                onClick={handleJiraHandoff}
                disabled={!canCreateJira}
                tone="secondary"
              />
            </div>

            {hasWarningsNeedingAcceptance ? (
              <label className="mt-5 flex items-center gap-3 text-sm text-slate-200/85">
                <input
                  aria-label="Accept validation warnings"
                  checked={warningsAccepted}
                  className="h-4 w-4 rounded border-white/20 bg-transparent"
                  onChange={(event) => setWarningsAccepted(event.target.checked)}
                  type="checkbox"
                />
                Accept warnings before Jira dry-run and creation.
              </label>
            ) : null}

            {dryRun ? (
              <div className="mt-5 rounded-[1.75rem] border border-white/10 bg-white/5 p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="text-xl text-white">Jira dry-run preview</h3>
                  <StatePill tone={dryRun.safe_to_execute ? "success" : "error"}>
                    {dryRun.safe_to_execute ? "Safe to execute" : "Not safe to execute"}
                  </StatePill>
                </div>
                <p className="mt-3 text-sm text-slate-300/80">
                  Estimated Jira objects: {dryRun.estimated_jira_objects} · Idempotency key:{" "}
                  {dryRun.idempotency_key}
                </p>
                <div className="mt-4 grid gap-4 xl:grid-cols-2">
                  <PayloadPreview title="Epic payload preview" payload={dryRun.epic_payload_preview.fields} />
                  <PayloadPreview
                    title="Child issue payload previews"
                    payload={dryRun.child_issue_payload_previews.map((item) => item.fields)}
                  />
                </div>
                {dryRun.validation_errors.length > 0 ? (
                  <ValidationPanel title="Dry-run errors" tone="error" messages={dryRun.validation_errors} />
                ) : null}
                {dryRun.validation_warnings.length > 0 ? (
                  <ValidationPanel title="Dry-run warnings" tone="warning" messages={dryRun.validation_warnings} />
                ) : null}
              </div>
            ) : null}

            {handoffResult ? (
              <div className="mt-5 rounded-[1.75rem] border border-emerald-300/20 bg-emerald-400/10 p-5 text-sm text-emerald-50/95">
                Jira epic created: <span className="font-semibold">{handoffResult.key}</span>
                {handoffResult.url ? (
                  <>
                    {" "}
                    ·{" "}
                    <a
                      className="font-semibold underline decoration-emerald-100/50 underline-offset-4"
                      href={handoffResult.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open epic in Jira
                    </a>
                  </>
                ) : null}

                {handoffResult.issues.length > 0 ? (
                  <div className="mt-4 space-y-2">
                    {handoffResult.issues.map((issue) => (
                      <div key={issue.key} className="rounded-[1rem] border border-emerald-200/20 bg-emerald-500/10 px-4 py-3">
                        <span className="font-semibold">{issue.key}</span> · {issue.summary} ·{" "}
                        {issue.assignee ? issue.assignee : "Unassigned"}
                        {issue.url ? (
                          <>
                            {" "}
                            ·{" "}
                            <a
                              className="font-semibold underline decoration-emerald-100/50 underline-offset-4"
                              href={issue.url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open
                            </a>
                          </>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </SurfaceSection>
        </div>
      </div>
    </main>
  );
}

<<<<<<< Updated upstream
function ReviewBlock({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
=======
function SectionPanel({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="surface-panel rounded-[2rem] p-6 sm:p-7">
      <p className="text-xs font-semibold uppercase tracking-[0.38em] text-contour-tide/90">
        {eyebrow}
      </p>
      <h2 className="mt-3 text-3xl text-white">{title}</h2>
      <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-300/80">{description}</p>
      <div className="mt-6">{children}</div>
    </section>
  );
}

function ReviewBlock({ title, children }: { title: string; children: ReactNode }) {
>>>>>>> Stashed changes
  return (
    <div className="mt-6">
      <h3 className="mb-4 text-2xl text-white">{title}</h3>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className={labelClassName}>{label}</span>
      {children}
    </label>
  );
}

function MetricTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | string;
  accent: "teal" | "blue" | "amber";
}) {
  const accentClass =
    accent === "teal"
      ? "from-contour-tide/30 to-contour-tide/5"
      : accent === "blue"
        ? "from-contour-aurora/30 to-contour-aurora/5"
        : "from-contour-sun/30 to-contour-sun/5";

  return (
    <div className={`rounded-[1.5rem] border border-white/10 bg-gradient-to-br ${accentClass} p-5`}>
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-300/80">{label}</p>
      <p className="mt-4 text-3xl text-white">{value}</p>
    </div>
  );
}

function CopyBlock({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-[1.5rem] border border-white/10 bg-slate-950/25 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-300/70">{title}</p>
      <p className="mt-3 text-sm leading-7 text-slate-100/90">{body}</p>
    </div>
  );
}

function StatusBanner({ banner }: { banner: BannerState }) {
  const className =
    banner.tone === "success"
      ? "border-emerald-300/20 bg-emerald-400/10 text-emerald-50"
      : banner.tone === "error"
        ? "border-red-300/20 bg-red-400/10 text-red-50"
        : "border-sky-300/20 bg-sky-400/10 text-sky-50";

  return <div className={`mb-6 rounded-[1.75rem] border p-4 text-sm ${className}`}>{banner.message}</div>;
}

function ValidationPanel({
  title,
  tone,
  messages,
}: {
  title: string;
  tone: "error" | "warning";
  messages: Array<{ code?: string; message: string; task_id?: string | null }>;
}) {
  const className =
    tone === "error"
      ? "border-red-300/20 bg-red-400/10 text-red-50"
      : "border-amber-300/20 bg-amber-400/10 text-amber-50";

  return (
    <div className={`mt-5 rounded-[1.75rem] border p-4 ${className}`}>
      <p className="text-sm font-semibold">{title}</p>
      <ul className="mt-3 space-y-2 text-sm">
        {messages.map((message, index) => (
          <li key={`${message.code ?? title}-${message.task_id ?? "global"}-${index}`}>
            {message.task_id ? `${message.task_id}: ` : ""}
            {message.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ActionButton({
  label,
  onClick,
  disabled,
  tone,
}: {
  label: string;
  onClick: () => void;
  disabled: boolean;
  tone: "primary" | "secondary";
}) {
  const className =
    tone === "primary"
      ? "bg-white text-slate-950 hover:bg-slate-100"
      : "bg-white/10 text-white hover:bg-white/15";

  return (
    <button
      className={`rounded-full px-5 py-3 text-sm font-semibold transition ${className} disabled:cursor-not-allowed disabled:opacity-50`}
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  );
}

function AssignmentBadge({ status }: { status: PlanItem["assignment_status"] }) {
  const tone =
    status === "assigned"
      ? "bg-emerald-400/15 text-emerald-100"
      : status === "assigned_with_skill_gap"
        ? "bg-amber-400/15 text-amber-100"
        : "bg-rose-400/15 text-rose-100";
  return (
    <div className={`rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] ${tone}`}>
      {status.replaceAll("_", " ")}
    </div>
  );
}

function StatePill({ children, tone }: { children: ReactNode; tone: "success" | "error" | "warning" | "info" }) {
  const className =
    tone === "success"
      ? "bg-emerald-400/15 text-emerald-100"
      : tone === "error"
        ? "bg-red-400/15 text-red-100"
        : tone === "warning"
          ? "bg-amber-400/15 text-amber-100"
          : "bg-slate-200/10 text-slate-100";
  return <div className={`rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] ${className}`}>{children}</div>;
}

function PayloadPreview({ title, payload }: { title: string; payload: unknown }) {
  return (
    <div className="rounded-[1.5rem] border border-white/10 bg-slate-950/25 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-300/70">{title}</p>
      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs leading-6 text-slate-100/85">
        {JSON.stringify(payload, null, 2)}
      </pre>
    </div>
  );
}

function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-100/85">
      {children}
    </span>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-[1.75rem] border border-dashed border-white/15 bg-white/5 p-6 text-sm text-slate-300/80">
      {message}
    </div>
  );
}

function emptyToNull(value: string) {
  const cleaned = value.trim();
  return cleaned.length > 0 ? cleaned : null;
}

function splitLines(value: string) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function splitCommaList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function previewAssignmentStatus(item: PlanItem, employee: EngineerProfile | null): PlanItem["assignment_status"] {
  if (!employee) {
    return "unassigned_capacity";
  }
  const matchingSkill = item.required_skills.some((skill) =>
    employee.skills.some((employeeSkill) => employeeSkill.toLowerCase() === skill.toLowerCase())
  );
  if (matchingSkill || item.required_skills.length === 0) {
    return "assigned";
  }
  return item.priority === "high" ? "assigned_with_skill_gap" : "unassigned_skill_gap";
}

function syncStatusToTone(status: string): "success" | "error" | "warning" | "info" {
  if (status === "SYNC_SUCCEEDED" || status === "DRY_RUN_PASSED") {
    return "success";
  }
  if (status === "SYNC_FAILED") {
    return "error";
  }
  if (status === "PARTIAL_FAILURE") {
    return "warning";
  }
  return "info";
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong.";
}

function formatValidationErrors(error: z.ZodError<SprintRequest>) {
  return error.issues.map((issue) => {
    const prefix = issue.path.length > 0 ? `${issue.path.join(".")}: ` : "";
    return `${prefix}${issue.message}`;
  });
}
