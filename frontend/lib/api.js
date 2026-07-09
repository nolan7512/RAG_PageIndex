export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8111";

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
