const DEFAULT_API_PORT = "8111";
const CONFIGURED_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "";

function resolveApiBase() {
  const fallback = `http://localhost:${DEFAULT_API_PORT}`;
  const configured = CONFIGURED_API_BASE || fallback;
  if (typeof window === "undefined") {
    return configured;
  }

  try {
    const url = new URL(configured);
    const pageHost = window.location.hostname;
    const configuredHostIsLocal = ["localhost", "127.0.0.1", "::1"].includes(url.hostname);
    const pageHostIsRemote = pageHost && !["localhost", "127.0.0.1", "::1"].includes(pageHost);
    if (configuredHostIsLocal && pageHostIsRemote) {
      url.hostname = pageHost;
    }
    return url.origin;
  } catch {
    return configured;
  }
}

export const API_BASE = resolveApiBase();

export async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const body = options.body;

  if (body && !(body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: "include"
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      message = data.detail || message;
    } catch {
      // keep default HTTP message
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}

export function downloadUrl(documentId) {
  return `${API_BASE}/documents/${documentId}/download`;
}
