import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PlannerForm } from "@/lib/planner";

import { useAuthSession } from "./use-auth-session";

vi.mock("@/lib/api", () => ({
  clearStoredCsrfToken: vi.fn(),
  getProfile: vi.fn(),
  logout: vi.fn(),
  storeCsrfToken: vi.fn(),
}));

describe("useAuthSession", () => {
  it("restores a persisted session from localStorage", async () => {
    const { getProfile } = await import("@/lib/api");
    window.localStorage.clear();
    localStorage.setItem("tripbreeze_user", "sara");
    localStorage.setItem(
      "tripbreeze_profile",
      JSON.stringify({
        home_city: "Berlin",
        passport_country: "Germany",
      }),
    );
    localStorage.setItem("tripbreeze_csrf_token", "csrf-123");
    vi.mocked(getProfile).mockResolvedValue({
      user_id: "sara",
      profile: {
        home_city: "Berlin",
        passport_country: "Germany",
      },
      csrf_token: "csrf-456",
    });

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

  it("persists auth updates and clears them", async () => {
    const { logout, storeCsrfToken, clearStoredCsrfToken } = await import("@/lib/api");
    vi.mocked(logout).mockResolvedValue(undefined);
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
      result.current.persistAuth("alex", { home_city: "Paris" }, "csrf-999");
    });
    expect(localStorage.getItem("tripbreeze_user")).toBe("alex");
    expect(result.current.profile?.home_city).toBe("Paris");
    expect(storeCsrfToken).toHaveBeenCalledWith("csrf-999");
    localStorage.setItem("tripbreeze_csrf_token", "csrf-999");

    act(() => {
      result.current.clearAuthSession();
    });
    expect(localStorage.getItem("tripbreeze_user")).toBeNull();
    expect(clearStoredCsrfToken).toHaveBeenCalled();
    expect(result.current.authenticatedUser).toBe("");
    await waitFor(() => expect(logout).toHaveBeenCalledWith("csrf-999"));
  });
});
