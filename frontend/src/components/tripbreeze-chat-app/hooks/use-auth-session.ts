import { useEffect, useState } from "react";

import { clearStoredCsrfToken, getProfile, logout, storeCsrfToken } from "@/lib/api";
import type { PlannerForm } from "@/lib/planner";
import type { UserProfile } from "@/lib/types";

export function useAuthSession({
  setForm,
  setEmailAddress,
}: {
  setForm: React.Dispatch<React.SetStateAction<PlannerForm>>;
  setEmailAddress: React.Dispatch<React.SetStateAction<string>>;
}) {
  const [authenticatedUser, setAuthenticatedUser] = useState("");
  const [profile, setProfile] = useState<UserProfile | null>(null);

  useEffect(() => {
    const savedUser = window.localStorage.getItem("tripbreeze_user");
    const savedProfile = window.localStorage.getItem("tripbreeze_profile");
    const savedCsrfToken = window.localStorage.getItem("tripbreeze_csrf_token");
    if (!savedUser || !savedProfile || !savedCsrfToken) {
      return;
    }
    try {
      const parsedProfile = JSON.parse(savedProfile) as UserProfile;
      void getProfile(savedUser)
        .then((result) => {
          setAuthenticatedUser(result.user_id);
          setProfile(result.profile);
          setForm((current) => ({
            ...current,
            userId: result.user_id,
            origin: result.profile.home_city ?? "",
          }));
          setEmailAddress(result.user_id);
          window.localStorage.setItem("tripbreeze_user", result.user_id);
          window.localStorage.setItem("tripbreeze_profile", JSON.stringify(result.profile));
          storeCsrfToken(result.csrf_token);
        })
        .catch(() => {
          window.localStorage.removeItem("tripbreeze_user");
          window.localStorage.removeItem("tripbreeze_profile");
          clearStoredCsrfToken();
        });
      setProfile(parsedProfile);
    } catch {
      window.localStorage.removeItem("tripbreeze_user");
      window.localStorage.removeItem("tripbreeze_profile");
      clearStoredCsrfToken();
    }
  }, [setEmailAddress, setForm]);

  function persistAuth(userId: string, nextProfile: UserProfile, csrfToken?: string) {
    setAuthenticatedUser(userId);
    setProfile(nextProfile);
    setForm((current) => ({ ...current, userId, origin: nextProfile.home_city ?? current.origin }));
    setEmailAddress(userId);
    window.localStorage.setItem("tripbreeze_user", userId);
    window.localStorage.setItem("tripbreeze_profile", JSON.stringify(nextProfile));
    if (csrfToken) {
      storeCsrfToken(csrfToken);
    }
  }

  function clearAuthSession() {
    const csrfToken = window.localStorage.getItem("tripbreeze_csrf_token") ?? "";
    setAuthenticatedUser("");
    setProfile(null);
    window.localStorage.removeItem("tripbreeze_user");
    window.localStorage.removeItem("tripbreeze_profile");
    clearStoredCsrfToken();
    void logout(csrfToken).catch(() => undefined);
  }

  return {
    authenticatedUser,
    profile,
    setProfile,
    persistAuth,
    clearAuthSession,
  };
}
