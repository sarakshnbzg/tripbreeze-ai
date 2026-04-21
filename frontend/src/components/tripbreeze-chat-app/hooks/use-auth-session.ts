import { useEffect, useState } from "react";

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
    if (!savedUser || !savedProfile) {
      return;
    }
    try {
      const parsedProfile = JSON.parse(savedProfile) as UserProfile;
      setAuthenticatedUser(savedUser);
      setProfile(parsedProfile);
      setForm((current) => ({
        ...current,
        userId: savedUser,
        origin: parsedProfile.home_city ?? "",
      }));
      setEmailAddress(savedUser);
    } catch {
      window.localStorage.removeItem("tripbreeze_user");
      window.localStorage.removeItem("tripbreeze_profile");
    }
  }, [setEmailAddress, setForm]);

  function persistAuth(userId: string, nextProfile: UserProfile) {
    setAuthenticatedUser(userId);
    setProfile(nextProfile);
    setForm((current) => ({ ...current, userId, origin: nextProfile.home_city ?? current.origin }));
    setEmailAddress(userId);
    window.localStorage.setItem("tripbreeze_user", userId);
    window.localStorage.setItem("tripbreeze_profile", JSON.stringify(nextProfile));
  }

  function clearAuthSession() {
    setAuthenticatedUser("");
    setProfile(null);
    window.localStorage.removeItem("tripbreeze_user");
    window.localStorage.removeItem("tripbreeze_profile");
  }

  return {
    authenticatedUser,
    profile,
    setProfile,
    persistAuth,
    clearAuthSession,
  };
}
