"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { z } from "zod";

import { plannerApi, PlannerApi } from "@/lib/api";
import {
  createEmptySprintRequest,
  createEmptyTask,
  EmployeeRecord,
  JiraHandoffResponse,
  PlanItem,
  SprintPlan,
  SprintRequest,
  sprintRequestSchema,
} from "@/lib/schemas";

type BannerTone = "success" | "error" | "info";
type PendingAction = "sample" | "generate" | "approve" | "handoff" | null;

type BannerState = {
  tone: BannerTone;
  message: string;
};

const inputClassName = "field-shell w-full";
const labelClassName = "mb-2 block text-xs font-semibold uppercase tracking-[0.28em] text-slate-300/75";
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
  const [handoffResult, setHandoffResult] = useState<JiraHandoffResponse | null>(null);
  const [banner, setBanner] = useState<BannerState | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
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

  const generateLabel = plan ? "Regenerate Draft" : "Generate Draft Plan";
  const handoffDisabled = !plan || plan.approval_state !== "approved" || pendingAction !== null;

  async function runAction<T>(action: Exclude<PendingAction, null>, work: () => Promise<T>) {
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

  function updatePlanItem(index: number, patch: Partial<PlanItem>) {
    setPlan((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        approval_state: "draft",
        plan_items: current.plan_items.map((item, itemIndex) =>
          itemIndex === index ? { ...item, ...patch } : item
        ),
      };
    });
  }

  function handleAssigneeChange(index: number, employeeId: string) {
    if (!plan) {
      return;
    }
    const item = plan.plan_items[index];
    const employee = employees.find((candidate) => candidate.id === employeeId) ?? null;

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
        setPlan(null);
        setHandoffResult(null);
        setValidationErrors([]);
        setBanner({ tone: "success", message: "Loaded sample sprint data." });
      } catch (error) {
        setBanner({ tone: "error", message: getErrorMessage(error) });
      }
    });
  }

  async function handleGeneratePlan() {
    const parsed = sprintRequestSchema.safeParse(request);
    if (!parsed.success) {
      setValidationErrors(formatValidationErrors(parsed.error));
      setBanner({ tone: "error", message: "Please fix the request details before generating a plan." });
      return;
    }

    await runAction("generate", async () => {
      try {
        const draftPlan = await apiClient.generatePlan(parsed.data);
        setPlan(draftPlan);
        setHandoffResult(null);
        setValidationErrors([]);
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
        const approvedPlan = await apiClient.approvePlan(plan);
        setPlan(approvedPlan);
        setBanner({ tone: "success", message: "Plan approved and ready for Jira handoff." });
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
        const result = await apiClient.handoffPlan(projectKey, plan);
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
            Contour normalizes freeform work requests, estimates story points, recommends ownership from
            the built-in employee roster, and keeps a human review gate before Jira creation.
          </p>
        </div>

        <div className="surface-panel flex w-full max-w-md flex-col gap-4 rounded-[2rem] p-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.32em] text-slate-300/70">Jira Handoff</p>
            <p className="mt-2 text-sm text-slate-300/85">
              Approval stays mandatory. The handoff action only unlocks once the reviewed draft is approved.
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

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <div className="grid gap-6">
          <SectionPanel
            eyebrow="Intake"
            title="Shape the sprint request"
            description="Enter the sprint goal and freeform tasks. Contour will use the built-in employee roster as planning context."
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
                  <h2 className="text-2xl text-white">Task List</h2>
                  <p className="mt-1 text-sm text-slate-300/75">
                    Add one natural-language task per card. Keep each task focused enough for Jira ticket generation.
                  </p>
                </div>
                <ActionButton
                  label="Add Task"
                  onClick={() => updateRequest({ tasks: [...request.tasks, createEmptyTask(request.tasks.length + 1)] })}
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
                    </div>

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
          </SectionPanel>

          <SectionPanel
            eyebrow="Roster"
            title="Built-in employee roster"
            description="Contour considers the full employee roster for every planning run and uses the Jira account IDs attached to each employee for assignment."
          >
            {employees.length > 0 ? (
              <div className="grid gap-4 lg:grid-cols-2">
                {employees.map((employee) => (
                  <div key={employee.id} className="rounded-[1.75rem] border border-white/10 bg-white/5 p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <h3 className="text-xl text-white">{employee.name}</h3>
                        <p className="mt-2 text-sm text-slate-300/80">{employee.role}</p>
                      </div>
                      <Tag>{employee.capacity_points} pts</Tag>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {employee.skills.map((skill) => (
                        <Tag key={`${employee.id}-${skill}`}>{skill}</Tag>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState message="Loading employee roster..." />
            )}
          </SectionPanel>
        </div>

        <div className="grid gap-6">
          <SectionPanel
            eyebrow="Draft Review"
            title="Inspect and edit the recommendation"
            description="Contour keeps issue type, points, assignee, and rationale editable before approval so the final Jira handoff stays intentional."
          >
            {plan ? (
              <>
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  <MetricTile label="Assigned Points" value={plan.capacity_summary.assigned_points} accent="teal" />
                  <MetricTile label="Unassigned Points" value={plan.capacity_summary.unassigned_points} accent="amber" />
                  <MetricTile label="Total Capacity" value={plan.capacity_summary.total_capacity_points} accent="blue" />
                  <MetricTile label="Remaining Capacity" value={plan.capacity_summary.remaining_points} accent="blue" />
                </div>

                <div className="mt-6 rounded-[1.75rem] border border-white/10 bg-white/5 p-5">
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.32em] text-slate-300/70">
                        Approval State
                      </p>
                      <h3 className="mt-2 text-2xl text-white">{capitalize(plan.approval_state)}</h3>
                    </div>
                    <div
                      className={`rounded-full px-4 py-2 text-sm font-semibold ${
                        plan.approval_state === "approved"
                          ? "bg-emerald-400/15 text-emerald-100"
                          : "bg-slate-200/10 text-slate-100"
                      }`}
                    >
                      {plan.approval_state === "approved" ? "Ready for Jira handoff" : "Awaiting approval"}
                    </div>
                  </div>
                  <p className="mt-4 text-sm leading-7 text-slate-300/80">{plan.goal}</p>
                </div>

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
                                employees.find(
                                  (employee) => employee.jira_account_id === item.recommended_assignee_account_id
                                )?.id ?? ""
                              }
                              onChange={(event) => handleAssigneeChange(index, event.target.value)}
                            >
                              <option value="">Unassigned</option>
                              {employees.map((employee) => (
                                <option key={employee.id} value={employee.id}>
                                  {employee.name}
                                </option>
                              ))}
                            </select>
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

                        {item.alternative_assignees.length > 0 ? (
                          <p className="mt-4 text-sm text-slate-300/75">
                            Alternatives: {item.alternative_assignees.join(", ")}
                          </p>
                        ) : null}

                        {item.risk_flags.length > 0 ? (
                          <div className="mt-4 space-y-3">
                            {item.risk_flags.map((risk) => (
                              <div
                                key={`${item.task_id}-${risk.category}-${risk.message}`}
                                className="rounded-[1.2rem] border border-white/10 bg-slate-950/25 p-4"
                              >
                                <div className="flex items-center gap-3">
                                  <RiskBadge severity={risk.severity} />
                                  <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-200/75">
                                    {risk.category}
                                  </p>
                                </div>
                                <p className="mt-3 text-sm leading-7 text-slate-100/90">{risk.message}</p>
                              </div>
                            ))}
                          </div>
                        ) : null}
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

                <ReviewBlock title="Risk Review">
                  {plan.risks.length > 0 ? (
                    <div className="space-y-3">
                      {plan.risks.map((risk) => (
                        <div key={`${risk.category}-${risk.message}`} className="rounded-[1.75rem] border border-white/10 bg-white/5 p-5">
                          <div className="flex flex-wrap items-center gap-3">
                            <RiskBadge severity={risk.severity} />
                            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-200/75">
                              {risk.category}
                            </p>
                          </div>
                          <p className="mt-3 text-base leading-7 text-slate-100">{risk.message}</p>
                          <p className="mt-3 text-sm leading-6 text-slate-300/80">
                            Suggested action: {risk.suggested_action}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-[1.75rem] border border-emerald-300/20 bg-emerald-400/10 p-5 text-sm text-emerald-50/90">
                      No major planning risks were flagged.
                    </div>
                  )}
                </ReviewBlock>
              </>
            ) : (
              <EmptyState message="Generate a draft to review normalized Jira tickets, point estimates, ownership, and risks." />
            )}
          </SectionPanel>

          <SectionPanel
            eyebrow="Approval"
            title="Finalize the Jira handoff"
            description="Approval runs a final backend repair pass over the edited draft before the Epic and child issues are created."
          >
            <div className="flex flex-wrap gap-3">
              <ActionButton
                label={pendingAction === "approve" ? "Approving..." : "Approve Plan"}
                onClick={handleApprovePlan}
                disabled={!plan || plan.approval_state === "approved" || pendingAction !== null}
                tone="primary"
              />
              <ActionButton
                label={pendingAction === "handoff" ? "Creating Jira Tickets..." : "Create Jira Epic + Tickets"}
                onClick={handleJiraHandoff}
                disabled={handoffDisabled}
                tone="secondary"
              />
            </div>

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
          </SectionPanel>
        </div>
      </div>
    </main>
  );
}

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
      <p className="text-xs font-semibold uppercase tracking-[0.38em] text-contour-tide/90">{eyebrow}</p>
      <h2 className="mt-3 text-3xl text-white">{title}</h2>
      <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-300/80">{description}</p>
      <div className="mt-6">{children}</div>
    </section>
  );
}

function ReviewBlock({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="mt-6">
      <h3 className="mb-4 text-2xl text-white">{title}</h3>
      {children}
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
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
  value: number;
  accent: "teal" | "blue" | "amber";
}) {
  const accentClass =
    accent === "teal"
      ? "from-contour-tide/30 to-contour-tide/5"
      : accent === "blue"
        ? "from-contour-aurora/30 to-contour-aurora/5"
        : "from-contour-sun/30 to-contour-sun/5";

  return (
    <div className={`rounded-[1.75rem] border border-white/10 bg-gradient-to-br ${accentClass} p-5`}>
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-200/70">{label}</p>
      <p className="mt-4 text-4xl text-white">{value}</p>
    </div>
  );
}

function CopyBlock({
  title,
  body,
}: {
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-[1.4rem] border border-white/10 bg-slate-950/25 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-300/70">{title}</p>
      <p className="mt-3 text-sm leading-7 text-slate-100/90">{body}</p>
    </div>
  );
}

function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-full border border-contour-tide/30 bg-contour-tide/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-contour-tide">
      {children}
    </span>
  );
}

function RiskBadge({ severity }: { severity: "low" | "medium" | "high" }) {
  const className =
    severity === "high"
      ? "bg-red-400/15 text-red-100"
      : severity === "medium"
        ? "bg-amber-300/15 text-amber-50"
        : "bg-sky-300/15 text-sky-50";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${className}`}>
      {severity}
    </span>
  );
}

function AssignmentBadge({ status }: { status: PlanItem["assignment_status"] }) {
  const className =
    status === "assigned"
      ? "bg-emerald-400/15 text-emerald-100"
      : status === "assigned_with_skill_gap"
        ? "bg-amber-300/15 text-amber-50"
        : status === "unassigned_skill_gap"
          ? "bg-red-300/15 text-red-100"
          : "bg-sky-300/15 text-sky-50";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${className}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-[1.75rem] border border-dashed border-white/15 bg-white/5 px-5 py-10 text-center text-sm leading-7 text-slate-300/80">
      {message}
    </div>
  );
}

function StatusBanner({ banner }: { banner: BannerState }) {
  const classes =
    banner.tone === "success"
      ? "border-emerald-300/20 bg-emerald-400/10 text-emerald-50"
      : banner.tone === "error"
        ? "border-red-300/20 bg-red-400/10 text-red-50"
        : "border-sky-300/20 bg-sky-400/10 text-sky-50";

  return <div className={`mb-6 rounded-[1.6rem] border px-5 py-4 text-sm font-medium ${classes}`}>{banner.message}</div>;
}

function ActionButton({
  label,
  onClick,
  disabled,
  tone,
}: {
  label: string;
  onClick: () => void | Promise<void>;
  disabled?: boolean;
  tone: "primary" | "secondary";
}) {
  const toneClasses =
    tone === "primary"
      ? "action-button bg-contour-tide text-slate-950 hover:bg-contour-tide/90"
      : "action-button border border-white/10 bg-white/[0.06] text-slate-50 hover:bg-white/[0.12]";

  return (
    <button className={toneClasses} disabled={disabled} onClick={onClick} type="button">
      {label}
    </button>
  );
}

function emptyToNull(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function getErrorMessage(error: unknown) {
  if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong. Please try again.";
}

function formatValidationErrors(error: z.ZodError<SprintRequest>) {
  return error.issues.map((issue) => {
    const [group, index, field] = issue.path;

    if (group === "tasks" && typeof index === "number") {
      return `Task ${index + 1} ${String(field).replaceAll("_", " ")}: ${issue.message}`;
    }

    return issue.message;
  });
}

function previewAssignmentStatus(
  item: PlanItem,
  employee: EmployeeRecord | null
): PlanItem["assignment_status"] {
  if (!employee) {
    return item.assignment_status.startsWith("unassigned") ? item.assignment_status : "unassigned_capacity";
  }

  const requiredSkills = new Set(item.required_skills.map((skill) => slugify(skill)));
  const employeeSkills = new Set(employee.skills.map((skill) => slugify(skill)));
  const hasSkillMatch =
    requiredSkills.size === 0 ||
    Array.from(requiredSkills).some((skill) => employeeSkills.has(skill));

  if (!hasSkillMatch) {
    return item.priority === "high" ? "assigned_with_skill_gap" : "unassigned_skill_gap";
  }
  return "assigned";
}

function slugify(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-");
}
