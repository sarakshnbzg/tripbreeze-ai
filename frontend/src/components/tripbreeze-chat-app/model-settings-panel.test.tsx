import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { defaultForm } from "@/lib/planner";

import { ModelSettingsPanel } from "./model-settings-panel";

describe("ModelSettingsPanel", () => {
  it("renders provider, model, and temperature controls", () => {
    const setForm = vi.fn();

    render(
      <ModelSettingsPanel
        form={{ ...defaultForm, provider: "openai", model: "gpt-4o-mini", temperature: 0.3 }}
        setForm={setForm}
        availableProviders={["openai", "gemini"]}
        availableModels={["gpt-4o-mini", "gpt-4.1-mini"]}
      />,
    );

    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(screen.getByText("Provider")).toBeInTheDocument();
    expect(screen.getByText("Model")).toBeInTheDocument();
    expect(screen.getByText("Temperature")).toBeInTheDocument();
    expect(screen.getByText("0.3")).toBeInTheDocument();

    const comboboxes = screen.getAllByRole("combobox");
    fireEvent.change(comboboxes[1], {
      target: { value: "gpt-4.1-mini" },
    });

    expect(setForm).toHaveBeenCalledTimes(1);
  });
});
