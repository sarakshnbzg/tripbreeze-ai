import type {
  ApproveRequest,
  AuthResponse,
  SearchRequest,
  StreamEvent,
  StreamEventType,
  UserProfile,
} from "@/lib/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8100";
const CSRF_STORAGE_KEY = "tripbreeze_csrf_token";
const CSRF_HEADER_NAME = "x-csrf-token";

function getStoredCsrfToken(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(CSRF_STORAGE_KEY) ?? "";
}

export function storeCsrfToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }
  if (token) {
    window.localStorage.setItem(CSRF_STORAGE_KEY, token);
  } else {
    window.localStorage.removeItem(CSRF_STORAGE_KEY);
  }
}

export function clearStoredCsrfToken(): void {
  storeCsrfToken("");
}

function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = new Headers(init?.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && !headers.has(CSRF_HEADER_NAME)) {
    const csrfToken = getStoredCsrfToken();
    if (csrfToken) {
      headers.set(CSRF_HEADER_NAME, csrfToken);
    }
  }
  return fetch(input, {
    credentials: "include",
    ...init,
    headers,
  });
}

async function readSseStream(
  response: Response,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  if (!response.ok) {
    throw new Error(await response.text());
  }

  if (!response.body) {
    throw new Error("Streaming response body is not available.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const lines = part.split("\n");
      let event: StreamEventType = "node_message";
      let data = "";

      for (const line of lines) {
        if (line.startsWith("event:")) {
          event = line.slice(6).trim() as StreamEventType;
        }
        if (line.startsWith("data:")) {
          data += line.slice(5).trim();
        }
      }

      if (!data) {
        continue;
      }

      try {
        onEvent({ event, data: JSON.parse(data) as Record<string, unknown> });
      } catch {
        onEvent({ event, data: { raw: data } });
      }
    }
  }
}

export async function streamSearch(
  request: SearchRequest,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  await readSseStream(response, onEvent);
}

export async function streamClarify(
  threadId: string,
  answer: string,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/api/search/${threadId}/clarify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer }),
  });
  await readSseStream(response, onEvent);
}

export async function streamApprove(
  threadId: string,
  request: ApproveRequest,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/api/search/${threadId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  await readSseStream(response, onEvent);
}

export async function fetchReturnFlights(
  threadId: string,
  params: {
    origin: string;
    destination: string;
    departure_date: string;
    return_date: string;
    departure_token: string;
    adults: number;
    travel_class: string;
    currency: string;
    return_time_window?: number[] | null;
  },
): Promise<Array<Record<string, unknown>>> {
  return parseJsonResponse<Array<Record<string, unknown>>>(
    await apiFetch(`${API_BASE_URL}/api/search/${encodeURIComponent(threadId)}/return-flights`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    }),
  );
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export async function login(userId: string, password: string): Promise<AuthResponse> {
  return parseJsonResponse<AuthResponse>(
    await apiFetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, password }),
    }),
  );
}

export async function register(userId: string, password: string, profile: UserProfile): Promise<AuthResponse> {
  return parseJsonResponse<AuthResponse>(
    await apiFetch(`${API_BASE_URL}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, password, profile }),
    }),
  );
}

export async function logout(csrfToken?: string): Promise<void> {
  const headers = csrfToken ? { [CSRF_HEADER_NAME]: csrfToken } : undefined;
  await parseJsonResponse<{ success: boolean }>(
    await apiFetch(`${API_BASE_URL}/api/auth/logout`, {
      method: "POST",
      headers,
    }),
  );
}

export async function getProfile(userId: string): Promise<AuthResponse> {
  return parseJsonResponse<AuthResponse>(
    await apiFetch(`${API_BASE_URL}/api/profile/${encodeURIComponent(userId)}`),
  );
}

export async function saveProfile(userId: string, profile: UserProfile): Promise<AuthResponse> {
  return parseJsonResponse<AuthResponse>(
    await apiFetch(`${API_BASE_URL}/api/profile/${encodeURIComponent(userId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile }),
    }),
  );
}

export async function getReferenceValues(category: string): Promise<string[]> {
  const payload = await parseJsonResponse<{ category: string; values: string[] }>(
    await apiFetch(`${API_BASE_URL}/api/reference-values/${encodeURIComponent(category)}`, {
      cache: "force-cache",
    }),
  );
  return payload.values;
}

export async function transcribeAudio(blob: Blob, filename = "recording.webm"): Promise<string> {
  const formData = new FormData();
  formData.append("file", blob, filename);
  const payload = await parseJsonResponse<{ text: string }>(
    await apiFetch(`${API_BASE_URL}/api/transcribe`, {
      method: "POST",
      body: formData,
    }),
  );
  return payload.text;
}

export async function downloadItineraryPdf(finalItinerary: string, graphState: Record<string, unknown>, fileName = "trip_itinerary.pdf"): Promise<Blob> {
  const response = await apiFetch(`${API_BASE_URL}/api/itinerary/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      final_itinerary: finalItinerary,
      graph_state: graphState,
      file_name: fileName,
    }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return await response.blob();
}

export async function emailItinerary(
  recipientEmail: string,
  recipientName: string,
  finalItinerary: string,
  graphState: Record<string, unknown>,
): Promise<{ success: boolean; message: string }> {
  return parseJsonResponse<{ success: boolean; message: string }>(
    await apiFetch(`${API_BASE_URL}/api/itinerary/email`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recipient_email: recipientEmail,
        recipient_name: recipientName,
        final_itinerary: finalItinerary,
        graph_state: graphState,
      }),
    }),
  );
}
