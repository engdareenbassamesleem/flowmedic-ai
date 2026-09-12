import type {
  ApiErrorBody,
  HealthResponse,
  Incident,
  IncidentPage,
  N8nConnectionResponse,
  SystemStatus,
  WorkflowPage,
} from "@/lib/types";

const apiBaseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...options,
      headers: { Accept: "application/json", ...options?.headers },
    });
  } catch {
    throw new ApiError("FlowMedic backend is unavailable. Check that the API is running.", 0);
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
    throw new ApiError(
      body.error?.message ?? "The request could not be completed.",
      response.status,
      body.error?.code,
    );
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  systemStatus: () => request<SystemStatus>("/api/v1/system/status"),
  n8nStatus: () => request<N8nConnectionResponse>("/api/v1/n8n/status"),
  workflows: (limit = 50, cursor?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    return request<WorkflowPage>(`/api/v1/workflows?${params}`);
  },
  incidents: (limit = 50, offset = 0) =>
    request<IncidentPage>(`/api/v1/incidents?limit=${limit}&offset=${offset}`),
  incident: (id: string) => request<Incident>(`/api/v1/incidents/${id}`),
  diagnose: (id: string) => request<Incident>(`/api/v1/incidents/${id}/diagnose`, { method: "POST" }),
};
