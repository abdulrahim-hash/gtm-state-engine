import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "@/app/page";

describe("M1D product shell", () => {
  it("clearly labels the synthetic demo and local dry-run boundary", () => {
    render(<Home />);

    expect(screen.getByRole("status")).toHaveTextContent("Synthetic public demo");
    expect(screen.getByRole("status")).toHaveTextContent("No prospect or client data");
    expect(screen.getByText("External execution remains off")).toBeInTheDocument();
    expect(screen.getByText("M1D / Local dry-run only")).toBeInTheDocument();
    expect(
      screen.getByText(/no seller task, CRM write, message, or external request/i),
    ).toBeInTheDocument();
  });

  it("links to the strategy and account evidence foundations", () => {
    render(<Home />);

    expect(screen.getByRole("link", { name: "Inspect strategy" })).toHaveAttribute(
      "href",
      "/strategy",
    );
    expect(screen.getByRole("link", { name: "Browse accounts" })).toHaveAttribute(
      "href",
      "/accounts",
    );
  });
});
