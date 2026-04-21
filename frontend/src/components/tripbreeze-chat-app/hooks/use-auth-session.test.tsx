import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PlannerForm } from "@/lib/planner";

import { useAuthSession } from "./use-auth-session";

describe("useAuthSession", () => {
  it("restores a persisted session from localStorage", async () => {
    window.localStorage.clear();
    localStorage.setItem("tripbreeze_user", "sara");
    localStorage.setItem(
      "tripbreeze_profile",
      JSON.stringify({
        home_city: "Berlin",
        passport_country: "Germany",
      }),
    );

    const setForm = vi.fn<(updater: React.SetStateAction<PlannerForm>) => void>();
    const setEmailAddress = vi.fn<(updater: React.SetStateAction<string>) => void>();

    const { result } = renderHook(() =>
      useAuthSession({
        setForm,
        setEmailAddress,
      }),
    );

    await waitFor(() => expect(result.current.authenticatedUser).toBe("sara"));
    expect(result.current.profile?.home_city).toBe("Berlin");
    expect(setForm).toHaveBeenCalled();
    expect(setEmailAddress).toHaveBeenCalledWith("sara");
  });

  it("persists auth updates and clears them", () => {
    window.localStorage.clear();
    const setForm = vi.fn<(updater: React.SetStateAction<PlannerForm>) => void>();
    const setEmailAddress = vi.fn<(updater: React.SetStateAction<string>) => void>();

    const { result } = renderHook(() =>
      useAuthSession({
        setForm,
        setEmailAddress,
      }),
    );

    act(() => {
      result.current.persistAuth("alex", { home_city: "Paris" });
    });
    expect(localStorage.getItem("tripbreeze_user")).toBe("alex");
    expect(result.current.profile?.home_city).toBe("Paris");

    act(() => {
      result.current.clearAuthSession();
    });
    expect(localStorage.getItem("tripbreeze_user")).toBeNull();
    expect(result.current.authenticatedUser).toBe("");
  });
});
