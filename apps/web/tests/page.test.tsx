import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "@/app/page";

describe("M1C product shell", () => {
  it("clearly labels the synthetic demo and non-executing M1C boundary", () => {
    render(<Home />);

    expect(screen.getByRole("status")).toHaveTextContent("Synthetic public demo");
    expect(screen.getByRole("status")).toHaveTextContent("No prospect or client data");
    expect(screen.getByText("Downstream execution remains off")).toBeInTheDocument();
    expect(screen.getByText("M1C / Proposed only")).toBeInTheDocument();
    expect(screen.getByText(/cannot authorize an external action/i)).toBeInTheDocument();
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
