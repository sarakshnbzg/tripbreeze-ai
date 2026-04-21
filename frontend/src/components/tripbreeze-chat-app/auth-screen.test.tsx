import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AuthScreen } from "./auth-screen";

function renderAuthScreen(mode: "login" | "register" = "login") {
  const setAuthMode = vi.fn();
  const setLoginForm = vi.fn();
  const setRegisterForm = vi.fn();
  const onLogin = vi.fn();
  const onRegister = vi.fn();

  render(
    <AuthScreen
      authMode={mode}
      setAuthMode={setAuthMode}
      loginForm={{ userId: "", password: "" }}
      setLoginForm={setLoginForm}
      registerForm={{
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
      }}
      setRegisterForm={setRegisterForm}
      cities={["Berlin"]}
      countries={["Germany"]}
      airlines={["Lufthansa"]}
      loading={null}
      error=""
      onLogin={onLogin}
      onRegister={onRegister}
    />,
  );

  return { setAuthMode, onLogin, onRegister };
}

describe("AuthScreen", () => {
  it("renders login mode and calls the login handler", () => {
    const { onLogin } = renderAuthScreen("login");

    fireEvent.click(screen.getAllByRole("button", { name: "Log In" })[1]);

    expect(screen.getByText("Welcome back")).toBeInTheDocument();
    expect(onLogin).toHaveBeenCalledTimes(1);
  });

  it("switches modes via the segmented control", () => {
    const { setAuthMode } = renderAuthScreen("login");

    fireEvent.click(screen.getByRole("button", { name: "Register" }));

    expect(setAuthMode).toHaveBeenCalledWith("register");
  });

  it("renders registration fields and submits registration", () => {
    const { onRegister } = renderAuthScreen("register");

    expect(screen.getByText("Account details")).toBeInTheDocument();
    expect(screen.getByText("Travel profile")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Register" })[1]);

    expect(onRegister).toHaveBeenCalledTimes(1);
  });
});
