import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarketingHomepage } from "@/components/marketing-homepage";

describe("MarketingHomepage", () => {
  it("renders the homepage story and sends visitors to the demo", () => {
    render(<MarketingHomepage />);
    const primaryNav = screen.getByRole("navigation", { name: /primary/i });

    expect(
      screen.getByRole("heading", {
        name: /turn sprint planning into a calmer, more confident decision/i,
      })
    ).toBeInTheDocument();

    expect(within(primaryNav).getByRole("link", { name: "Product" })).toHaveAttribute(
      "href",
      "/#product"
    );
    expect(within(primaryNav).getByRole("link", { name: "How It Works" })).toHaveAttribute(
      "href",
      "/#how-it-works"
    );
    expect(within(primaryNav).getByRole("link", { name: "Who It's For" })).toHaveAttribute(
      "href",
      "/#who-its-for"
    );
    expect(within(primaryNav).getByRole("link", { name: "Pricing" })).toHaveAttribute(
      "href",
      "/#pricing"
    );
    expect(within(primaryNav).getByRole("link", { name: "FAQ" })).toHaveAttribute("href", "/#faq");

    expect(
      screen
        .getAllByRole("link", { name: /open demo/i })
        .some((link) => link.getAttribute("href") === "/demo")
    ).toBe(true);

    expect(
      screen.getByRole("heading", {
        name: /a planning workspace that stays grounded in the real sprint/i,
      })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /how contour keeps planning grounded/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /built for the people carrying sprint planning/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /simple packaging while the product takes shape/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /questions teams ask before trying it/i })
    ).toBeInTheDocument();
  });
});
