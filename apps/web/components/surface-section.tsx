import type { ReactNode } from "react";

export function SurfaceSection({
  eyebrow,
  title,
  description,
  children,
  className = "",
  contentClassName = "",
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
}) {
  return (
    <section className={`surface-panel rounded-[2rem] p-6 sm:p-7 ${className}`.trim()}>
      <p className="text-xs font-semibold uppercase tracking-[0.38em] text-contour-tide/90">{eyebrow}</p>
      <h2 className="mt-3 text-3xl text-white">{title}</h2>
      <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-300/80">{description}</p>
      <div className={`mt-6 ${contentClassName}`.trim()}>{children}</div>
    </section>
  );
}
