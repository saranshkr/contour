"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import { z } from "zod";

import { plannerApi, PlannerApi } from "@/lib/api";
import { SurfaceSection } from "@/components/surface-section";
import {
  BacklogItem,
  createEmptyBacklogItem,
  createEmptySprintRequest,
  createEmptyTeamMember,
  JiraHandoffResponse,
  SprintPlan,
  SprintRequest,
  TeamMember,
  sprintRequestSchema,
} from "@/lib/schemas";

type BannerTone = "success" | "error" | "info";
type PendingAction = "sample" | "generate" | "approve" | "handoff" | null;

type BannerState = {
  tone: BannerTone;
  message: string;
};

const inputClassName =
  "field-shell w-full";

const labelClassName = "mb-2 block text-xs font-semibold uppercase tracking-[0.28em] text-slate-300/75";

export function PlannerWorkspace({
  apiClient = plannerApi,
}: {
  apiClient?: PlannerApi;
}) {
  const [request, setRequest] = useState<SprintRequest>(createEmptySprintRequest());
  const [projectKey, setProjectKey] = useState("CTR");
  const [plan, setPlan] = useState<SprintPlan | null>(null);
  const [handoffResult, setHandoffResult] = useState<JiraHandoffResponse | null>(null);
  const [banner, setBanner] = useState<BannerState | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);

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

  function updateBacklogItem(index: number, patch: Partial<BacklogItem>) {
    setRequest((current) => ({
      ...current,
      backlog_items: current.backlog_items.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...patch } : item
      ),
    }));
  }

  function updateTeamMember(index: number, patch: Partial<TeamMember>) {
    setRequest((current) => ({
      ...current,
      team_members: current.team_members.map((member, memberIndex) =>
        memberIndex === index ? { ...member, ...patch } : member
      ),
    }));
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
            Turn backlog context into an approval-ready sprint plan.
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-200/80 sm:text-lg">
            Contour combines structured intake, AI-backed recommendations, explicit risk review, and a
            human approval gate before Jira handoff.
          </p>
        </div>

        <div className="surface-panel flex w-full max-w-md flex-col gap-4 rounded-[2rem] p-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.32em] text-slate-300/70">Jira Handoff</p>
            <p className="mt-2 text-sm text-slate-300/85">
              Approval stays mandatory. The handoff action only unlocks once the draft is approved.
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
                <p className="mt-1 text-sm text-slate-300/75">Model each candidate item with priority, labels, dependencies, and owner hints.</p>
              </div>
              <ActionButton
                label="Add Backlog Item"
                onClick={() =>
                  updateRequest({
                    backlog_items: [...request.backlog_items, createEmptyBacklogItem(request.backlog_items.length + 1)],
                  })
                }
                disabled={pendingAction !== null}
                tone="secondary"
              />
            </div>

            <div className="space-y-4">
              {request.backlog_items.map((item, index) => (
                <div key={`${item.id}-${index}`} className="rounded-[1.75rem] border border-white/10 bg-white/5 p-5">
                  <div className="mb-4 flex items-center justify-between gap-4">
                    <p className="text-sm font-semibold uppercase tracking-[0.28em] text-slate-300/70">
                      Item {index + 1}
                    </p>
                    {request.backlog_items.length > 1 ? (
                      <button
                        className="text-sm font-semibold text-red-200 transition hover:text-red-100"
                        onClick={() =>
                          updateRequest({
                            backlog_items: request.backlog_items.filter((_, itemIndex) => itemIndex !== index),
                          })
                        }
                        type="button"
                      >
                        Remove
                      </button>
                    ) : null}
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <Field label="Item ID">
                      <input
                        aria-label={`Backlog item ${index + 1} id`}
                        className={inputClassName}
                        value={item.id}
                        onChange={(event) => updateBacklogItem(index, { id: event.target.value })}
                      />
                    </Field>
                    <Field label="Priority">
                      <select
                        aria-label={`Backlog item ${index + 1} priority`}
                        className={inputClassName}
                        value={item.priority}
                        onChange={(event) => updateBacklogItem(index, { priority: event.target.value })}
                      >
                        {["Critical", "High", "Medium", "Low"].map((priority) => (
                          <option key={priority} value={priority}>
                            {priority}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Title">
                      <input
                        aria-label={`Backlog item ${index + 1} title`}
                        className={inputClassName}
                        value={item.title}
                        onChange={(event) => updateBacklogItem(index, { title: event.target.value })}
                      />
                    </Field>
                    <Field label="Owner Hint">
                      <input
                        aria-label={`Backlog item ${index + 1} owner hint`}
                        className={inputClassName}
                        value={item.owner_hint ?? ""}
                        onChange={(event) =>
                          updateBacklogItem(index, { owner_hint: emptyToNull(event.target.value) })
                        }
                        placeholder="Optional"
                      />
                    </Field>
                  </div>

                  <div className="mt-4 grid gap-4 md:grid-cols-2">
                    <Field label="Description">
                      <textarea
                        aria-label={`Backlog item ${index + 1} description`}
                        className={`${inputClassName} min-h-32`}
                        value={item.description}
                        onChange={(event) => updateBacklogItem(index, { description: event.target.value })}
                      />
                    </Field>
                    <div className="grid gap-4">
                      <Field label="Labels">
                        <input
                          aria-label={`Backlog item ${index + 1} labels`}
                          className={inputClassName}
                          value={item.labels.join(", ")}
                          onChange={(event) =>
                            updateBacklogItem(index, { labels: splitCommaSeparated(event.target.value) })
                          }
                          placeholder="frontend, planning, jira"
                        />
                      </Field>
                      <Field label="Dependencies">
                        <input
                          aria-label={`Backlog item ${index + 1} dependencies`}
                          className={inputClassName}
                          value={item.dependencies.join(", ")}
                          onChange={(event) =>
                            updateBacklogItem(index, { dependencies: splitCommaSeparated(event.target.value) })
                          }
                          placeholder="CTR-101, CTR-109"
                        />
                      </Field>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-8">
            <div className="mb-4 flex items-center justify-between gap-4">
              <div>
                <h2 className="text-2xl text-white">Team Context</h2>
                <p className="mt-1 text-sm text-slate-300/75">Capture roles, current skill coverage, and point capacity for each teammate.</p>
              </div>
              <ActionButton
                label="Add Team Member"
                onClick={() =>
                  updateRequest({
                    team_members: [...request.team_members, createEmptyTeamMember(request.team_members.length + 1)],
                  })
                }
                disabled={pendingAction !== null}
                tone="secondary"
              />
            </div>

            <div className="space-y-4">
              {request.team_members.map((member, index) => (
                <div key={`${member.name}-${index}`} className="rounded-[1.75rem] border border-white/10 bg-white/5 p-5">
                  <div className="mb-4 flex items-center justify-between gap-4">
                    <p className="text-sm font-semibold uppercase tracking-[0.28em] text-slate-300/70">
                      Member {index + 1}
                    </p>
                    {request.team_members.length > 1 ? (
                      <button
                        className="text-sm font-semibold text-red-200 transition hover:text-red-100"
                        onClick={() =>
                          updateRequest({
                            team_members: request.team_members.filter((_, memberIndex) => memberIndex !== index),
                          })
                        }
                        type="button"
                      >
                        Remove
                      </button>
                    ) : null}
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <Field label="Name">
                      <input
                        aria-label={`Team member ${index + 1} name`}
                        className={inputClassName}
                        value={member.name}
                        onChange={(event) => updateTeamMember(index, { name: event.target.value })}
                      />
                    </Field>
                    <Field label="Role">
                      <input
                        aria-label={`Team member ${index + 1} role`}
                        className={inputClassName}
                        value={member.role}
                        onChange={(event) => updateTeamMember(index, { role: event.target.value })}
                      />
                    </Field>
                    <Field label="Skills">
                      <input
                        aria-label={`Team member ${index + 1} skills`}
                        className={inputClassName}
                        value={member.skills.join(", ")}
                        onChange={(event) => updateTeamMember(index, { skills: splitCommaSeparated(event.target.value) })}
                        placeholder="frontend, jira, python"
                      />
                    </Field>
                    <Field label="Capacity Points">
                      <input
                        aria-label={`Team member ${index + 1} capacity points`}
                        className={inputClassName}
                        type="number"
                        min={0}
                        value={String(member.capacity_points)}
                        onChange={(event) =>
                          updateTeamMember(index, {
                            capacity_points: Number.parseInt(event.target.value || "0", 10) || 0,
                          })
                        }
                      />
                    </Field>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </SurfaceSection>

        <div className="grid gap-6">
          <SurfaceSection
            eyebrow="Draft Review"
            title="Inspect the recommendation"
            description="Contour keeps the reasoning visible so sprint decisions stay explainable."
          >
            {plan ? (
              <>
                <div className="grid gap-4 sm:grid-cols-3">
                  <MetricTile label="Selected Points" value={plan.capacity_summary.selected_points} accent="teal" />
                  <MetricTile label="Total Capacity" value={plan.capacity_summary.total_capacity_points} accent="blue" />
                  <MetricTile label="Remaining Capacity" value={plan.capacity_summary.remaining_points} accent="amber" />
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

                <ReviewBlock title="Selected Sprint Items">
                  {plan.selected_items.length > 0 ? (
                    <div className="space-y-4">
                      {plan.selected_items.map((item) => (
                        <div key={item.id} className="rounded-[1.75rem] border border-white/10 bg-white/5 p-5">
                          <div className="flex flex-wrap items-start justify-between gap-4">
                            <div>
                              <h4 className="text-xl text-white">
                                {item.id} · {item.title}
                              </h4>
                              <p className="mt-2 text-sm text-slate-300/80">
                                {item.estimated_points} pts · Owner: {item.recommended_assignee}
                              </p>
                            </div>
                            {item.required_skills.length > 0 ? (
                              <div className="flex flex-wrap gap-2">
                                {item.required_skills.map((skill) => (
                                  <Tag key={skill}>{skill}</Tag>
                                ))}
                              </div>
                            ) : null}
                          </div>

                          <div className="mt-4 grid gap-4 lg:grid-cols-2">
                            <CopyBlock title="Selection rationale" body={item.selection_rationale} />
                            <CopyBlock title="Assignment rationale" body={item.assignment_rationale} />
                          </div>

                          {item.alternative_assignees.length > 0 ? (
                            <p className="mt-4 text-sm text-slate-300/75">
                              Alternatives: {item.alternative_assignees.join(", ")}
                            </p>
                          ) : null}
                          {item.ambiguity_flags.length > 0 ? (
                            <p className="mt-2 text-sm text-amber-100/90">
                              Ambiguity: {item.ambiguity_flags.join(", ")}
                            </p>
                          ) : null}
                          {item.dependency_signals.length > 0 ? (
                            <p className="mt-2 text-sm text-sky-100/90">
                              Dependencies: {item.dependency_signals.join(", ")}
                            </p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState message="No sprint items were selected." />
                  )}
                </ReviewBlock>

                <ReviewBlock title="Deferred Items">
                  {plan.deferred_items.length > 0 ? (
                    <div className="space-y-3">
                      {plan.deferred_items.map((item) => (
                        <div key={item.id} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4 text-sm text-slate-200/85">
                          {item.id} · {item.title} ({item.estimated_points} pts)
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState message="No items were deferred." />
                  )}
                </ReviewBlock>

                <ReviewBlock title="Capacity by Team Member">
                  <div className="overflow-hidden rounded-[1.75rem] border border-white/10">
                    <table className="min-w-full divide-y divide-white/10 text-left text-sm text-slate-100">
                      <thead className="bg-white/5 text-xs uppercase tracking-[0.24em] text-slate-300/75">
                        <tr>
                          <th className="px-4 py-3">Member</th>
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
              <EmptyState message="Generate a draft to review selected work, ownership, capacity, and risks." />
            )}
          </SurfaceSection>

          <SurfaceSection
            eyebrow="Approval"
            title="Finalize the sprint plan"
            description="Approval is a deliberate human step before the Jira artifact can be created."
          >
            <div className="flex flex-wrap gap-3">
              <ActionButton
                label={pendingAction === "approve" ? "Approving..." : "Approve Plan"}
                onClick={handleApprovePlan}
                disabled={!plan || plan.approval_state === "approved" || pendingAction !== null}
                tone="primary"
              />
              <ActionButton
                label={pendingAction === "handoff" ? "Creating Jira Epic..." : "Create Jira Plan Epic"}
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
                    <a className="font-semibold underline decoration-emerald-100/50 underline-offset-4" href={handoffResult.url} target="_blank" rel="noreferrer">
                      Open in Jira
                    </a>
                  </>
                ) : null}
              </div>
            ) : null}
          </SurfaceSection>
        </div>
      </div>
    </main>
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

  return (
    <div className={`mb-6 rounded-[1.6rem] border px-5 py-4 text-sm font-medium ${classes}`}>{banner.message}</div>
  );
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

function splitCommaSeparated(value: string) {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
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

    if (group === "backlog_items" && typeof index === "number") {
      return `Backlog item ${index + 1} ${String(field).replaceAll("_", " ")}: ${issue.message}`;
    }

    if (group === "team_members" && typeof index === "number") {
      return `Team member ${index + 1} ${String(field).replaceAll("_", " ")}: ${issue.message}`;
    }

    return issue.message;
  });
}
