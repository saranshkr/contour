import type { ReactNode } from "react";

type SiteNavLink = {
  href: string;
  label: string;
};

const defaultLinks: SiteNavLink[] = [
  { href: "/#product", label: "Product" },
  { href: "/#how-it-works", label: "How It Works" },
  { href: "/#who-its-for", label: "Who It's For" },
  { href: "/#pricing", label: "Pricing" },
  { href: "/#faq", label: "FAQ" },
];

export function SiteHeader({
  links = defaultLinks,
  ctaHref,
  ctaLabel,
  ctaVariant = "primary",
}: {
  links?: SiteNavLink[];
  ctaHref: string;
  ctaLabel: string;
  ctaVariant?: "primary" | "secondary";
}) {
  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-slate-950/20 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4 sm:px-8 lg:px-10">
        <a className="flex items-center gap-3 text-sm font-semibold uppercase tracking-[0.34em] text-slate-100" href="/">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-contour-tide/30 bg-contour-tide/10 text-contour-tide">
            C
          </span>
          Contour
        </a>

        <nav aria-label="Primary" className="hidden items-center gap-6 text-sm text-slate-200/80 md:flex">
          {links.map((link) => (
            <a
              key={`${link.href}-${link.label}`}
              className="transition hover:text-white"
              href={link.href}
            >
              {link.label}
            </a>
          ))}
        </nav>

        <SiteButton href={ctaHref} variant={ctaVariant}>
          {ctaLabel}
        </SiteButton>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t border-white/10">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-8 text-sm text-slate-300/75 sm:flex-row sm:items-center sm:justify-between sm:px-8 lg:px-10">
        <p>Contour helps teams turn backlog context into an approval-ready sprint plan.</p>
        <div className="flex flex-wrap items-center gap-4">
          {defaultLinks.map((link) => (
            <a key={`${link.href}-footer`} className="transition hover:text-white" href={link.href}>
              {link.label}
            </a>
          ))}
          <a className="transition hover:text-white" href="/demo">
            Demo
          </a>
        </div>
      </div>
    </footer>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="max-w-3xl">
      <p className="text-xs font-semibold uppercase tracking-[0.38em] text-contour-tide/90">{eyebrow}</p>
      <h2 className="mt-3 text-3xl leading-tight text-white sm:text-4xl">{title}</h2>
      <p className="mt-4 text-base leading-7 text-slate-200/80">{description}</p>
    </div>
  );
}

export function SiteButton({
  href,
  children,
  variant = "primary",
  className = "",
}: {
  href: string;
  children: ReactNode;
  variant?: "primary" | "secondary";
  className?: string;
}) {
  const variantClassName =
    variant === "primary"
      ? "bg-contour-tide text-slate-950 hover:bg-contour-tide/90"
      : "border border-white/10 bg-white/[0.06] text-slate-50 hover:bg-white/[0.12]";

  return (
    <a
      className={`inline-flex items-center justify-center rounded-full px-5 py-3 text-sm font-semibold transition duration-200 ${variantClassName} ${className}`.trim()}
      href={href}
    >
      {children}
    </a>
  );
}
