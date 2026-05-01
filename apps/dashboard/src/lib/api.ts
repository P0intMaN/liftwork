// Thin typed fetch wrapper. Vite dev server proxies /api → :7878.
import { clearToken, getToken } from "./auth";
import type {
  ActivityItem,
  Application,
  BuildRun,
  Cluster,
  CurrentUser,
  Deployment,
  MetricsSummary,
  TimeseriesPoint,
  UUID,
} from "./types";

const BASE = "/api";

class ApiError extends Error {
  constructor(public status: number, public body: unknown, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  headers.set("accept", "application/json");
  if (init.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  if (token) headers.set("authorization", `Bearer ${token}`);

  const res = await fetch(`${BASE}${path}`, { ...init, headers });

  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  const isJson = ct.includes("application/json");
  const body = isJson ? await res.json() : await res.text();

  if (!res.ok) {
    if (res.status === 401) clearToken();
    throw new ApiError(
      res.status,
      body,
      typeof body === "object" && body && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `request failed: ${res.status}`,
    );
  }
  return body as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; expires_in: number }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<CurrentUser>("/auth/me"),

  listClusters: () => request<Cluster[]>("/clusters"),
  createCluster: (input: {
    name: string;
    display_name: string;
    default_namespace?: string;
    in_cluster?: boolean;
  }) =>
    request<Cluster>("/clusters", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  listApplications: () => request<Application[]>("/applications"),
  getApplication: (id: UUID) => request<Application>(`/applications/${id}`),
  createApplication: (input: Omit<Application, "id" | "created_at" | "updated_at">) =>
    request<Application>("/applications", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  deleteApplication: (id: UUID) =>
    request<void>(`/applications/${id}`, { method: "DELETE" }),

  listBuilds: (applicationId: UUID) =>
    request<BuildRun[]>(`/applications/${applicationId}/builds`),
  triggerBuild: (applicationId: UUID) =>
    request<{ build_id: UUID; status: string }>(
      `/applications/${applicationId}/builds`,
      { method: "POST" },
    ),
  getBuild: (buildId: UUID) => request<BuildRun>(`/builds/${buildId}`),

  listDeployments: (applicationId: UUID) =>
    request<Deployment[]>(`/applications/${applicationId}/deployments`),
  getDeployment: (id: UUID) => request<Deployment>(`/deployments/${id}`),

  summary: (sinceDays = 30) =>
    request<MetricsSummary>(`/dashboard/summary?since_days=${sinceDays}`),
  buildsTimeseries: (days = 30) =>
    request<TimeseriesPoint[]>(`/dashboard/builds/timeseries?days=${days}`),
  deploysTimeseries: (days = 30) =>
    request<TimeseriesPoint[]>(`/dashboard/deploys/timeseries?days=${days}`),
  activity: (limit = 50) =>
    request<ActivityItem[]>(`/dashboard/activity?limit=${limit}`),
};

export { ApiError };

/**
 * SSE log stream via fetch + ReadableStream. EventSource can't carry
 * Authorization headers, so we parse the SSE protocol manually.
 */
export async function* streamBuildLogs(
  buildId: UUID,
  signal?: AbortSignal,
): AsyncGenerator<{ data?: string; event?: string }> {
  const token = getToken();
  const headers = new Headers({ accept: "text/event-stream" });
  if (token) headers.set("authorization", `Bearer ${token}`);

  const res = await fetch(`${BASE}/builds/${buildId}/logs`, { headers, signal });
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, null, `log stream failed: ${res.status}`);
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      buffer += value;
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        if (!frame.trim()) continue;
        const data: string[] = [];
        let eventName: string | undefined;
        for (const line of frame.split("\n")) {
          if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
          else if (line.startsWith("event:")) eventName = line.slice(6).trim();
        }
        if (data.length || eventName) {
          yield { data: data.join("\n"), event: eventName };
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
