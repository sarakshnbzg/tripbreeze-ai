import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthController } from "./use-auth-controller";

vi.mock("@/lib/api", () => ({
  getProfile: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
  saveProfile: vi.fn(),
}));

describe("useAuthController", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sets a profile save confirmation after a successful save", async () => {
    const persistAuth = vi.fn();
    const setLoading = vi.fn();
    const setError = vi.fn();
    const { saveProfile } = await import("@/lib/api");

    vi.mocked(saveProfile).mockResolvedValue({
      user_id: "sara",
      profile: { home_city: "Berlin" },
    });

    const { result } = renderHook(() =>
      useAuthController({
        authenticatedUser: "sara",
        profile: { home_city: "Berlin" },
        persistAuth,
        setLoading,
        setError,
      }),
    );

    await act(async () => {
      await result.current.handleSaveProfile();
    });

    expect(persistAuth).toHaveBeenCalledWith("sara", { home_city: "Berlin" });
    expect(result.current.profileSaveMessage).toBe("Profile saved.");
  });

  it("clears the save confirmation when asked", async () => {
    const persistAuth = vi.fn();
    const setLoading = vi.fn();
    const setError = vi.fn();
    const { saveProfile } = await import("@/lib/api");

    vi.mocked(saveProfile).mockResolvedValue({
      user_id: "sara",
      profile: { home_city: "Berlin" },
    });

    const { result } = renderHook(() =>
      useAuthController({
        authenticatedUser: "sara",
        profile: { home_city: "Berlin" },
        persistAuth,
        setLoading,
        setError,
      }),
    );

    await act(async () => {
      await result.current.handleSaveProfile();
    });

    act(() => {
      result.current.clearProfileSaveMessage();
    });

    await waitFor(() => {
      expect(result.current.profileSaveMessage).toBe("");
    });
  });
});
