import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  api: {
    incidents: vi.fn().mockResolvedValue({ data: [] }),
    workflows: vi.fn().mockResolvedValue({ data: [] }),
    systemStatus: vi.fn().mockResolvedValue({ n8n_configured: false, ai_mode: "mock", database_engine: "sqlite" }),
  },
}));

import OverviewPage from "@/app/page";

describe("OverviewPage", () => {
  it("renders an honest empty incident state", async () => {
    render(<OverviewPage />);
    expect(screen.getByRole("heading", { name: "Automation health" })).toBeInTheDocument();
    expect(await screen.findByText("No incidents yet")).toBeInTheDocument();
    expect(screen.getByText("n8n not configured")).toBeInTheDocument();
  });
});
