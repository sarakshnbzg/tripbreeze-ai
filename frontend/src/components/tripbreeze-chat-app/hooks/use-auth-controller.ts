import { useState } from "react";

import { login, register, saveProfile } from "@/lib/api";
import { expandStarThresholds, safeErrorMessage } from "@/components/tripbreeze-chat-app/helpers";
import type { UserProfile } from "@/lib/types";

import type {
  AuthMode,
  LoginFormState,
  PlannerLoadingState,
  RegisterFormState,
} from "../ui-types";

const DEFAULT_LOGIN_FORM: LoginFormState = {
  userId: "",
  password: "",
};

const DEFAULT_REGISTER_FORM: RegisterFormState = {
  userId: "",
  password: "",
  confirmPassword: "",
  homeCity: "",
  passportCountry: "",
  travelClass: "ECONOMY",
  preferredAirlines: [],
  preferredHotelStars: [],
  outboundWindowStart: 0,
  outboundWindowEnd: 23,
  returnWindowStart: 0,
  returnWindowEnd: 23,
};

export function useAuthController({
  authenticatedUser,
  profile,
  persistAuth,
  setLoading,
  setError,
}: {
  authenticatedUser: string;
  profile: UserProfile | null;
  persistAuth: (userId: string, profile: UserProfile) => void;
  setLoading: React.Dispatch<React.SetStateAction<PlannerLoadingState>>;
  setError: React.Dispatch<React.SetStateAction<string>>;
}) {
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [loginForm, setLoginForm] = useState<LoginFormState>(DEFAULT_LOGIN_FORM);
  const [registerForm, setRegisterForm] = useState<RegisterFormState>(DEFAULT_REGISTER_FORM);

  async function handleLogin() {
    setError("");
    setLoading("auth");
    try {
      const result = await login(loginForm.userId.trim(), loginForm.password);
      persistAuth(result.user_id, result.profile);
    } catch (authError) {
      setError(safeErrorMessage(authError));
    } finally {
      setLoading(null);
    }
  }

  async function handleRegister() {
    setError("");
    if (registerForm.password !== registerForm.confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading("auth");
    try {
      const result = await register(registerForm.userId.trim(), registerForm.password, {
        home_city: registerForm.homeCity,
        passport_country: registerForm.passportCountry,
        travel_class: registerForm.travelClass,
        preferred_airlines: registerForm.preferredAirlines,
        preferred_hotel_stars: expandStarThresholds(registerForm.preferredHotelStars),
        preferred_outbound_time_window: [
          registerForm.outboundWindowStart,
          registerForm.outboundWindowEnd,
        ],
        preferred_return_time_window: [
          registerForm.returnWindowStart,
          registerForm.returnWindowEnd,
        ],
      });
      persistAuth(result.user_id, result.profile);
    } catch (authError) {
      setError(safeErrorMessage(authError));
    } finally {
      setLoading(null);
    }
  }

  async function handleSaveProfile() {
    if (!authenticatedUser || !profile) {
      return;
    }

    setError("");
    setLoading("saving");
    try {
      const result = await saveProfile(authenticatedUser, profile);
      persistAuth(result.user_id, result.profile);
    } catch (saveError) {
      setError(safeErrorMessage(saveError));
    } finally {
      setLoading(null);
    }
  }

  return {
    authMode,
    setAuthMode,
    loginForm,
    setLoginForm,
    registerForm,
    setRegisterForm,
    handleLogin,
    handleRegister,
    handleSaveProfile,
  };
}
