import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "@/app/page";

describe("M1B.1 product shell", () => {
  it("clearly labels the synthetic demo and M1B.1 boundary", () => {
    render(<Home />);

    expect(screen.getByRole("status")).toHaveTextContent("Synthetic public demo");
    expect(screen.getByRole("status")).toHaveTextContent("No prospect or client data");
    expect(screen.getByText("Downstream logic remains off")).toBeInTheDocument();
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
