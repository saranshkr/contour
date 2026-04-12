import type { Metadata } from "next";

import { PlannerWorkspace } from "@/components/planner-workspace";
import { SiteFooter, SiteHeader } from "@/components/site-chrome";
import { SurfaceSection } from "@/components/surface-section";

export const metadata: Metadata = {
  title: "Contour Demo",
  description: "Explore the Contour sprint planning workspace and approval-first Jira handoff flow.",
};

export default function DemoPage() {
  return (
    <div className="relative isolate">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[22rem] bg-[radial-gradient(circle_at_top_left,rgba(119,186,248,0.18),transparent_28%),radial-gradient(circle_at_top_right,rgba(240,163,87,0.12),transparent_26%)]" />
      <SiteHeader ctaHref="/" ctaLabel="Back Home" ctaVariant="secondary" />

      <div className="mx-auto max-w-7xl px-5 pt-8 sm:px-8 lg:px-10">
        <SurfaceSection
          eyebrow="Live Demo"
          title="Explore the full planning workspace"
          description="This page keeps the real planner front and center. Use sample data, generate a draft, review the reasoning, approve the plan, and walk through the Jira handoff flow."
        >
          <div className="flex flex-wrap gap-3 text-sm text-slate-200/80">
            <a className="font-semibold text-contour-tide transition hover:text-contour-tide/80" href="/">
              Return to the homepage
            </a>
            <span className="text-slate-500">/</span>
            <span>Current API contracts and planner behavior stay unchanged on this route.</span>
          </div>
        </SurfaceSection>
      </div>

      <PlannerWorkspace />
      <SiteFooter />
    </div>
  );
}
