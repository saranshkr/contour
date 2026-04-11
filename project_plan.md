# Contour MVP Development Plan

## 1. Project Summary

**Project name:** Contour

**Goal:**  
Build an AI sprint planning copilot that analyzes backlog items and team capacity, recommends sprint scope and assignees, highlights planning risks, and hands off the approved plan to the existing Jira creation workflow.

## 2. MVP Objective

The MVP should help a team lead or product owner answer:

- What should go into the next sprint?
- Who should own each selected item?
- Where are the obvious risks in the plan?
- How can the approved plan be turned into a Jira-ready artifact?

## 3. In-Scope Outcomes

The MVP must support:

- backlog intake
- team roster and capacity intake
- sprint item selection
- assignee recommendation
- rationale generation
- risk flagging
- review and approval
- handoff to Jira creation workflow

## 4. Out of Scope

The MVP will not include:

- calendar scheduling
- Slack or email delegation
- onboarding workflows
- blocker meeting automation
- multi-sprint planning
- autonomous reprioritization after approval
- full work-management platform features
- real-time sync across enterprise tools

## 5. Product Boundaries

The MVP is a **planning copilot**, not an autonomous manager.

It should:
- recommend
- explain
- flag
- hand off for approval

It should not:
- make irreversible planning decisions without approval
- expand into general team management
- attempt to automate every agile workflow

## 6. Core Modules

The MVP should be organized into the following product modules:

1. **Backlog Intake Module**
2. **Team Context Module**
3. **Ticket Analysis Module**
4. **Sprint Planning Module**
5. **Assignment Recommendation Module**
6. **Risk Review Module**
7. **Approval Module**
8. **Jira Handoff Module**

## 7. Phase Plan

---

## Phase 0 — Scope Lock

**Objective:**  
Freeze the MVP boundaries before development begins.

**Outputs:**
- final project name
- final one-line product definition
- final list of in-scope features
- final list of out-of-scope features
- final definition of the user and usage scenario

**Exit criteria:**
- team agrees on one clear MVP statement
- no ambiguous “nice-to-have” feature remains in the core scope

---

## Phase 1 — Input Contract Definition

**Objective:**  
Define the minimum information the system needs in order to produce a sprint plan.

**Outputs:**
- backlog item schema
- team member schema
- capacity schema
- optional metadata schema for priority, dependencies, and ownership context

**Exit criteria:**
- all required input fields are defined
- sample input set is agreed upon
- missing-field handling rules are documented

---

## Phase 2 — Planning Output Definition

**Objective:**  
Define exactly what the system must produce after planning.

**Outputs:**
- sprint recommendation format
- assignee recommendation format
- rationale format
- risk flag format
- approval-ready plan summary format
- Jira handoff payload definition

**Exit criteria:**
- output structure is frozen
- every output field has a clear purpose
- approval state is clearly defined

---

## Phase 3 — Ticket Understanding Layer

**Objective:**  
Create the system behavior for interpreting backlog items before planning begins.

**Responsibilities:**
- identify likely required skills
- estimate effort bucket
- detect ambiguity
- detect basic dependency signals
- normalize inconsistent backlog language

**Outputs:**
- enriched backlog representation
- confidence or uncertainty markers for unclear tickets

**Exit criteria:**
- each backlog item can be transformed into a planning-ready representation
- unclear tickets are explicitly identified instead of silently passed through

---

## Phase 4 — Sprint Selection Layer

**Objective:**  
Determine which backlog items should fit into the sprint.

**Responsibilities:**
- evaluate priority
- evaluate sprint fit
- respect overall team capacity
- reject low-fit or high-risk items when needed

**Outputs:**
- selected sprint items
- deferred items
- selection rationale

**Exit criteria:**
- the system can explain why an item was included or excluded
- selection stays within defined capacity boundaries

---

## Phase 5 — Assignment Recommendation Layer

**Objective:**  
Recommend ownership for each selected item.

**Responsibilities:**
- match item needs to team skills
- consider current capacity
- consider ownership relevance or experience signals
- avoid obviously imbalanced allocations

**Outputs:**
- recommended assignee per selected item
- ranked alternatives if needed
- assignment rationale

**Exit criteria:**
- every selected item has a proposed owner
- each assignment has a short explanation
- workload distribution is visibly reasonable

---

## Phase 6 — Risk Review Layer

**Objective:**  
Review the proposed sprint plan for obvious delivery issues.

**Responsibilities:**
- detect overload
- detect skill gaps
- detect vague items
- detect dependency concerns
- surface planning warnings for review

**Outputs:**
- risk list
- severity labels
- suggested review actions

**Exit criteria:**
- the system can produce a concise risk summary
- at least the main avoidable planning issues are surfaced before approval

---

## Phase 7 — Approval and Plan Finalization

**Objective:**  
Convert the generated recommendation into an approval-ready sprint plan.

**Responsibilities:**
- summarize the sprint
- summarize ownership
- summarize capacity usage
- summarize top risks
- support human approval or revision

**Outputs:**
- final approved sprint plan
- final plan summary
- final approval state

**Exit criteria:**
- the plan can be reviewed as one coherent artifact
- the system distinguishes clearly between draft and approved plan

---

## Phase 8 — Jira Handoff

**Objective:**  
Pass the approved sprint plan into the existing Jira creation workflow.

**Responsibilities:**
- translate approved plan into Jira-ready content
- preserve the human-in-the-loop approval boundary
- ensure the created Jira artifact reflects the final approved plan

**Outputs:**
- Jira handoff artifact
- final creation status
- confirmation state for downstream workflow

**Exit criteria:**
- approved plans can be handed off cleanly
- Jira creation is treated as the final step, not the planning core

---

## Phase 9 — QA and MVP Hardening

**Objective:**  
Stabilize the MVP so it behaves predictably for the hackathon scenario.

**Responsibilities:**
- validate happy path end-to-end
- validate incomplete-input handling
- validate low-confidence backlog items
- validate overloaded-team scenarios
- validate Jira handoff readiness

**Outputs:**
- MVP validation checklist
- known limitations list
- final polish pass

**Exit criteria:**
- the full planning flow works from intake to Jira handoff
- failure cases are understandable
- known limitations are documented

## 8. Functional Acceptance Criteria

The MVP is complete when it can:

- accept backlog and team inputs
- convert backlog into planning-ready items
- recommend a sprint scope
- recommend assignees
- generate rationale for the main choices
- flag major risks
- produce an approval-ready plan
- hand the approved result to the Jira creation workflow

## 9. Quality Bar

The MVP should be judged by the following standards:

- **Clarity:** recommendations are understandable
- **Credibility:** assignments look realistic
- **Constraint-awareness:** sprint scope respects capacity
- **Transparency:** risks and uncertainty are surfaced
- **Modularity:** each planning stage is clearly separable
- **Human control:** approval happens before Jira creation

## 10. Suggested Development Order

Build in this order:

1. scope lock
2. input contracts
3. output contracts
4. ticket understanding
5. sprint selection
6. assignment recommendation
7. risk review
8. approval flow
9. Jira handoff
10. validation and hardening

## 11. Post-MVP Expansion Paths

These are intentionally deferred until after the hackathon:

- story/task-level Jira expansion beyond the initial sprint artifact
- deeper dependency reasoning
- workload history integration
- blocker detection from live comments or activity
- calendar-aware planning
- Slack or communication workflows
- multi-sprint roadmap planning
- onboarding assistance for new team members

## 12. Final Product Definition

**Contour** is a planning copilot for engineering teams that turns backlog items and team context into an approval-ready sprint plan with recommended scope, ownership, and risk visibility, then hands the approved result to Jira creation.
