import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { defaultForm } from "@/lib/planner";

import { ModelSettingsPanel } from "./model-settings-panel";

describe("ModelSettingsPanel", () => {
  it("renders model and temperature controls", () => {
    const setForm = vi.fn();

    render(
      <ModelSettingsPanel
        form={{ ...defaultForm, provider: "openai", model: "gpt-4o-mini", temperature: 0.3 }}
        setForm={setForm}
        availableModels={["gpt-4o-mini", "gpt-4.1-mini"]}
      />,
    );

    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(screen.getByText("Model")).toBeInTheDocument();
    expect(screen.getByText("Temperature")).toBeInTheDocument();
    expect(screen.getByText("0.3")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "gpt-4.1-mini" },
    });

    expect(setForm).toHaveBeenCalledTimes(1);
  });
});
