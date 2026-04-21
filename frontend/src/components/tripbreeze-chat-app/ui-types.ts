export type PlannerLoadingState =
  | "auth"
  | "planning"
  | "clarifying"
  | "approving"
  | "saving"
  | "voice"
  | "pdf"
  | "email"
  | null;

export type AuthMode = "login" | "register";

export type LoginFormState = {
  userId: string;
  password: string;
};

export type RegisterFormState = {
  userId: string;
  password: string;
  confirmPassword: string;
  homeCity: string;
  passportCountry: string;
  travelClass: string;
  preferredAirlines: string[];
  preferredHotelStars: number[];
  outboundWindowStart: number;
  outboundWindowEnd: number;
  returnWindowStart: number;
  returnWindowEnd: number;
};
