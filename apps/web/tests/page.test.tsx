import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "@/app/page";

describe("M0 product shell", () => {
  it("clearly labels the synthetic demo environment", () => {
    render(<Home />);

    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent("Synthetic demo environment");
    expect(banner).toHaveTextContent("No prospect or client data");
  });

  it("communicates the product purpose and safety boundary", () => {
    render(<Home />);

    expect(
      screen.getByRole("heading", { name: /know who matters.*see why now/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("External actions disabled")).toBeInTheDocument();
    expect(screen.getByText(/GTM domain data begins in M1/i)).toBeInTheDocument();
  });

  it("shows the complete auditable operating loop without fabricated metrics", () => {
    render(<Home />);

    for (const stage of [
      "Strategy",
      "Evidence",
      "Signal",
      "State",
      "Decision",
      "Policy",
      "Action",
      "Outcome",
    ]) {
      expect(screen.getByText(stage)).toBeInTheDocument();
    }
  });
});
