// Mirrors liftwork-api response schemas. Kept minimal — we type only what
// the UI actually consumes. Generated types from openapi.json are a v2 nicety.

export type UUID = string;

export interface Cluster {
  id: UUID;
  name: string;
  display_name: string;
  in_cluster: boolean;
  default_namespace: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Application {
  id: UUID;
  slug: string;
  display_name: string;
  repo_url: string;
  repo_owner: string;
  repo_name: string;
  default_branch: string;
  cluster_id: UUID;
  namespace: string;
  image_repository: string;
  auto_deploy: boolean;
  created_at: string;
  updated_at: string;
}

export type BuildStatus =
  | "queued"
  | "running"
  | "building"
  | "pushing"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface BuildRun {
  id: UUID;
  application_id: UUID;
  commit_sha: string;
  commit_message: string | null;
  branch: string;
  source: "webhook" | "manual" | "api" | "retry";
  status: BuildStatus;
  image_tag: string | null;
  image_digest: string | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export type DeploymentStatus =
  | "pending"
  | "applying"
  | "rolling_out"
  | "succeeded"
  | "failed"
  | "rolled_back";

export interface Deployment {
  id: UUID;
  application_id: UUID;
  build_run_id: UUID | null;
  cluster_id: UUID;
  namespace: string;
  image_tag: string;
  image_digest: string | null;
  status: DeploymentStatus;
  revision: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface BuildsSummary {
  total: number;
  succeeded: number;
  failed: number;
  in_flight: number;
  avg_duration_seconds: number;
  since_days: number;
}

export interface DeploysSummary {
  total: number;
  succeeded: number;
  failed: number;
  since_days: number;
}

export interface MetricsSummary {
  builds: BuildsSummary;
  deploys: DeploysSummary;
  applications: number;
  clusters: number;
}

export interface TimeseriesPoint {
  day: string;
  total: number;
  succeeded: number;
  failed: number;
}

export interface ActivityItem {
  kind: "build" | "deploy";
  id: UUID;
  application_id: UUID;
  application_slug: string | null;
  status: string;
  detail: string | null;
  created_at: string;
}

export interface CurrentUser {
  id: UUID;
  email: string;
  role: string;
  is_active: boolean;
}
