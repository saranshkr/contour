"use client";

import { useState } from "react";

export type FaqItem = {
  question: string;
  answer: string;
};

export function FaqAccordion({ items }: { items: FaqItem[] }) {
  const [openQuestion, setOpenQuestion] = useState<string | null>(null);

  function toggleQuestion(question: string) {
    setOpenQuestion((current) => (current === question ? null : question));
  }

  return (
    <div className="mt-8 space-y-4">
      {items.map((item) => {
        const isOpen = openQuestion === item.question;
        const panelId = `faq-${slugify(item.question)}`;
        const buttonId = `${panelId}-trigger`;

        return (
          <div
            key={item.question}
            className={`surface-panel rounded-[1.8rem] border p-5 transition ${
              isOpen ? "border-contour-tide/30" : "border-white/10"
            }`}
          >
            <button
              aria-controls={panelId}
              aria-expanded={isOpen}
              id={buttonId}
              className="flex w-full items-center justify-between gap-4 text-left"
              onClick={() => toggleQuestion(item.question)}
              type="button"
            >
              <span className="text-lg font-semibold text-white">{item.question}</span>
              <svg
                aria-hidden="true"
                className={`h-5 w-5 shrink-0 origin-center transition-transform duration-300 ease-out motion-reduce:transition-none ${
                  isOpen ? "rotate-180 text-contour-tide" : "text-slate-200/80"
                }`}
                fill="none"
                viewBox="0 0 20 20"
              >
                <path
                  d="m5.5 7.5 4.5 5 4.5-5"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.8"
                />
              </svg>
            </button>

            <div
              aria-hidden={!isOpen}
              aria-labelledby={buttonId}
              className={`grid overflow-hidden transition-[grid-template-rows,opacity,margin] duration-300 ease-out motion-reduce:transition-none ${
                isOpen ? "mt-4 grid-rows-[1fr] opacity-100" : "mt-0 grid-rows-[0fr] opacity-0"
              }`}
              id={panelId}
              role="region"
            >
              <div className="min-h-0">
                <p className="max-w-3xl text-sm leading-7 text-slate-300/80">{item.answer}</p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function slugify(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}
