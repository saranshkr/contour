import { SectionHeading, SiteButton, SiteFooter, SiteHeader } from "@/components/site-chrome";

const planningSignals = [
  {
    label: "Structured intake",
    detail: "Guide the sprint with backlog details, team skills, and actual capacity before AI gets involved.",
  },
  {
    label: "Explainable reasoning",
    detail: "Keep selection rationale, ownership recommendations, and planning risks visible to the team.",
  },
  {
    label: "Approval-first handoff",
    detail: "Hold the human review gate in place before anything is pushed into Jira.",
  },
];

const workflowSteps = [
  {
    step: "01",
    title: "Shape the sprint request",
    body: "Capture the sprint goal, candidate backlog items, owner hints, dependencies, and team capacity in one place.",
  },
  {
    step: "02",
    title: "Generate a grounded draft",
    body: "Contour proposes what fits, who should own it, and where the plan already looks fragile.",
  },
  {
    step: "03",
    title: "Review with visible reasoning",
    body: "Selected work, deferred work, capacity usage, and risks stay visible so the team can challenge the draft.",
  },
  {
    step: "04",
    title: "Approve and hand off cleanly",
    body: "Once the plan is approved, the Jira handoff stays deliberate and traceable instead of accidental.",
  },
];

const roleCards = [
  {
    title: "Engineering leads",
    body: "Use Contour to balance scope, skills, and delivery risk without manually stitching together every planning input.",
  },
  {
    title: "Product managers",
    body: "See which work truly supports the sprint goal and where ambiguity or dependency risk needs discussion first.",
  },
  {
    title: "Planning owners",
    body: "Keep the planning conversation structured and approval-driven instead of scattered across tickets, docs, and chat.",
  },
];

const featureCards = [
  {
    title: "Backlog context, not just prompts",
    body: "The planner starts from structured item, team, and capacity inputs so the recommendation stays grounded.",
  },
  {
    title: "Capacity and assignment in one view",
    body: "See selected points, remaining capacity, and recommended owners without jumping between tools.",
  },
  {
    title: "Risk review built into the flow",
    body: "Overload, ambiguity, and dependency signals are surfaced before the plan becomes real work in Jira.",
  },
  {
    title: "A real demo, not a mockup",
    body: "The live demo route is the actual planner UI already wired to the current API contracts.",
  },
];

const pricingCards = [
  {
    name: "Starter",
    detail: "For small teams shaping their first approval-first planning workflow.",
    price: "Placeholder",
    highlight: "A clean way to trial structured intake, AI-assisted planning, and Jira handoff.",
  },
  {
    name: "Team",
    detail: "For growing product and engineering teams that want a calmer sprint planning ritual.",
    price: "Placeholder",
    highlight: "Adds room for a steadier planning cadence and shared review around the draft.",
  },
  {
    name: "Enterprise",
    detail: "For organizations that care deeply about approval boundaries and predictable handoff.",
    price: "Placeholder",
    highlight: "Positioned for deeper rollout planning once packaging and controls are finalized.",
  },
];

const faqItems = [
  {
    question: "Does Contour automatically push work into Jira?",
    answer:
      "No. Jira handoff stays locked until the sprint plan is explicitly approved, which keeps the approval boundary intact.",
  },
  {
    question: "Is this meant for engineering managers only?",
    answer:
      "No. The product is aimed at the people who actually carry sprint planning forward, especially engineering leads, PMs, and delivery owners.",
  },
  {
    question: "How much of the current experience is real?",
    answer:
      "The demo route uses the existing planner workspace and API flow already in this repository rather than a separate marketing-only prototype.",
  },
  {
    question: "Is pricing finalized yet?",
    answer:
      "Not yet. The current pricing section is intentionally a placeholder so the website feels complete without locking final commercial decisions.",
  },
];

export function MarketingHomepage() {
  return (
    <div className="relative isolate overflow-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[44rem] bg-[radial-gradient(circle_at_top_left,rgba(119,186,248,0.22),transparent_30%),radial-gradient(circle_at_top_right,rgba(240,163,87,0.16),transparent_28%),radial-gradient(circle_at_center,rgba(109,211,199,0.08),transparent_45%)]" />
      <SiteHeader ctaHref="/demo" ctaLabel="Open Demo" />

      <main className="mx-auto max-w-7xl px-5 pb-24 pt-8 sm:px-8 lg:px-10">
        <section className="grid gap-8 pb-16 pt-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:pb-24">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-[0.42em] text-contour-tide/90">
              Sprint Planning Copilot
            </p>
            <h1 className="mt-5 text-5xl leading-tight text-white sm:text-6xl">
              Turn sprint planning into a calmer, more confident decision.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-200/80">
              Contour helps engineering leads and PMs turn backlog context into an explainable draft plan,
              keep approval in the loop, and hand the final decision off to Jira with less friction.
            </p>
            <div className="mt-8 flex flex-wrap gap-4">
              <SiteButton href="/demo">Open Demo</SiteButton>
              <SiteButton href="#how-it-works" variant="secondary">
                See How It Works
              </SiteButton>
            </div>
          </div>

          <div className="surface-panel rounded-[2.2rem] p-6 sm:p-7">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.32em] text-slate-300/70">Live Product Shape</p>
                <h2 className="mt-3 text-3xl text-white">What the current demo already proves</h2>
              </div>
              <span className="rounded-full border border-contour-tide/30 bg-contour-tide/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-contour-tide">
                Built now
              </span>
            </div>

            <div className="mt-6 space-y-4">
              {planningSignals.map((signal) => (
                <div
                  key={signal.label}
                  className="rounded-[1.75rem] border border-white/10 bg-gradient-to-br from-white/8 to-white/0 p-5"
                >
                  <p className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-100">{signal.label}</p>
                  <p className="mt-3 text-sm leading-7 text-slate-300/80">{signal.detail}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="pb-16" id="product">
          <SectionHeading
            eyebrow="Product"
            title="A planning workspace that stays grounded in the real sprint"
            description="Contour is not trying to replace the people making planning decisions. It helps teams organize the inputs, generate a thoughtful draft, and keep review visible before Jira handoff."
          />
          <div className="mt-8 grid gap-5 md:grid-cols-3">
            {planningSignals.map((signal) => (
              <FeatureCard key={`product-${signal.label}`} title={signal.label} body={signal.detail} />
            ))}
          </div>
        </section>

        <section className="pb-16" id="how-it-works">
          <SectionHeading
            eyebrow="How It Works"
            title="How Contour keeps planning grounded"
            description="The workflow follows the same sequence already present in the product: intake, generate, review, approve, and only then hand off."
          />
          <div className="mt-8 grid gap-5 lg:grid-cols-2">
            {workflowSteps.map((step) => (
              <div
                key={step.step}
                className="surface-panel rounded-[1.9rem] p-6"
              >
                <p className="text-xs font-semibold uppercase tracking-[0.32em] text-contour-sun/90">
                  Step {step.step}
                </p>
                <h3 className="mt-3 text-2xl text-white">{step.title}</h3>
                <p className="mt-4 text-sm leading-7 text-slate-300/80">{step.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="pb-16" id="who-its-for">
          <SectionHeading
            eyebrow="Who It's For"
            title="Built for the people carrying sprint planning"
            description="Contour is strongest for teams that already know planning should stay human-led, but want a more structured and explainable workflow around it."
          />
          <div className="mt-8 grid gap-5 md:grid-cols-3">
            {roleCards.map((role) => (
              <FeatureCard key={role.title} title={role.title} body={role.body} />
            ))}
          </div>
        </section>

        <section className="pb-16">
          <SectionHeading
            eyebrow="Highlights"
            title="A few reasons the product feels tangible already"
            description="The website should look polished, but it should also point back to actual capabilities that exist in the current experience."
          />
          <div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
            {featureCards.map((feature) => (
              <FeatureCard key={feature.title} title={feature.title} body={feature.body} compact />
            ))}
          </div>
        </section>

        <section className="pb-16" id="pricing">
          <SectionHeading
            eyebrow="Pricing"
            title="Simple packaging while the product takes shape"
            description="These tiers are placeholders for now. They are here to make the website feel complete without pretending pricing is already final."
          />
          <div className="mt-8 grid gap-5 lg:grid-cols-3">
            {pricingCards.map((plan) => (
              <div
                key={plan.name}
                className={`surface-panel rounded-[2rem] p-6 ${
                  plan.name === "Team" ? "ring-1 ring-contour-tide/35" : ""
                }`}
              >
                <p className="text-xs font-semibold uppercase tracking-[0.32em] text-slate-300/70">{plan.name}</p>
                <p className="mt-5 text-4xl text-white">{plan.price}</p>
                <p className="mt-4 text-sm leading-7 text-slate-300/80">{plan.detail}</p>
                <p className="mt-5 rounded-[1.5rem] border border-white/10 bg-white/5 px-4 py-4 text-sm leading-7 text-slate-100/90">
                  {plan.highlight}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="pb-16" id="faq">
          <SectionHeading
            eyebrow="FAQ"
            title="Questions teams ask before trying it"
            description="A few answers that make the product boundaries and current reality clear."
          />
          <div className="mt-8 space-y-4">
            {faqItems.map((item) => (
              <details
                key={item.question}
                className="surface-panel rounded-[1.8rem] p-5 open:border-contour-tide/30"
              >
                <summary className="cursor-pointer list-none text-lg font-semibold text-white">
                  {item.question}
                </summary>
                <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-300/80">{item.answer}</p>
              </details>
            ))}
          </div>
        </section>

        <section className="pb-8">
          <div className="surface-panel rounded-[2.3rem] p-8 sm:p-10">
            <p className="text-xs font-semibold uppercase tracking-[0.38em] text-contour-tide/90">Final CTA</p>
            <h2 className="mt-4 max-w-3xl text-4xl leading-tight text-white">
              Explore the planner workflow in the live demo and see how the approval-first handoff feels.
            </h2>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-200/80">
              The demo route uses the actual planning workspace in this repo, so the site story and the product behavior stay aligned.
            </p>
            <div className="mt-8 flex flex-wrap gap-4">
              <SiteButton href="/demo">Open Demo</SiteButton>
              <SiteButton href="#product" variant="secondary">
                Revisit the Product Story
              </SiteButton>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}

function FeatureCard({
  title,
  body,
  compact = false,
}: {
  title: string;
  body: string;
  compact?: boolean;
}) {
  return (
    <div className={`surface-panel rounded-[1.9rem] p-6 ${compact ? "h-full" : ""}`.trim()}>
      <h3 className="text-2xl text-white">{title}</h3>
      <p className="mt-4 text-sm leading-7 text-slate-300/80">{body}</p>
    </div>
  );
}
