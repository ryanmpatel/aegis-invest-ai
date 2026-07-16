// Minimal typed API client. Sends cookies and the CSRF token (double-submit).

const CSRF_KEY = "aegis_csrf_token";

export function setCsrfToken(token: string) {
  sessionStorage.setItem(CSRF_KEY, token);
}

export function clearCsrfToken() {
  sessionStorage.removeItem(CSRF_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") {
    const csrf = sessionStorage.getItem(CSRF_KEY);
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  const response = await fetch(path, {
    method,
    headers,
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = data.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, String(detail));
  }
  if (response.headers.get("content-type")?.includes("text/csv")) {
    return (await response.text()) as unknown as T;
  }
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
};
