import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ClarificationPanel, PlanningProgressPanel } from "./planner-stage-panels";

describe("planner stage panels", () => {
  it("toggles compact planning progress details", () => {
    const setShowPlanningProgress = vi.fn();

    render(
      <PlanningProgressPanel
        recentPlanningUpdates={["Searching flights", "Checking hotels"]}
        showPlanningProgress={false}
        setShowPlanningProgress={setShowPlanningProgress}
        loading="planning"
        compact
      />,
    );

    expect(screen.getByText("Planning progress")).toBeInTheDocument();
    expect(screen.queryByText("Searching flights")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /planning progress/i }));

    expect(setShowPlanningProgress).toHaveBeenCalledTimes(1);
  });

  it("submits clarification answers only when text is present", () => {
    const setClarificationAnswer = vi.fn();
    const handleClarification = vi.fn(async () => undefined);

    render(
      <ClarificationPanel
        clarificationQuestion="Which departure city should I use?"
        clarificationAnswer="Berlin"
        setClarificationAnswer={setClarificationAnswer}
        handleClarification={handleClarification}
        loading={null}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("Type your answer here..."), {
      target: { value: "Munich" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue Planning" }));

    expect(setClarificationAnswer).toHaveBeenCalledTimes(1);
    expect(handleClarification).toHaveBeenCalledTimes(1);
  });
});
