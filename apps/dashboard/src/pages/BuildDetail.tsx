import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, GitCommit } from "lucide-react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LogStream } from "@/components/LogStream";
import { PipelineSteps, type PipelineStep } from "@/components/PipelineSteps";
import { StatusBadge } from "@/components/StatusBadge";
import { Skeleton } from "@/components/ui/skeleton";
import { absTime, formatDuration, shortSha } from "@/lib/format";
import type { BuildRun } from "@/lib/types";

export default function BuildDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const build = useQuery({
    queryKey: ["build", id],
    queryFn: () => api.getBuild(id),
    refetchInterval: (q) =>
      q.state.data && ["succeeded", "failed", "cancelled"].includes(q.state.data.status)
        ? false
        : 3000,
  });
  const app = useQuery({
    queryKey: ["app", build.data?.application_id],
    queryFn: () => api.getApplication(build.data!.application_id),
    enabled: !!build.data,
  });

  return (
    <>
      <PageHeader
        title={build.data ? `${shortSha(build.data.commit_sha)} · ${build.data.branch}` : "Build"}
        subtitle={
          build.data
            ? build.data.commit_message ?? `commit ${shortSha(build.data.commit_sha, 12)}`
            : ""
        }
        actions={
          <Button variant="ghost" asChild>
            <Link to={app.data ? `/applications/${app.data.id}` : "/applications"}>
              <ArrowLeft className="h-4 w-4" /> {app.data?.display_name ?? "Back"}
            </Link>
          </Button>
        }
      />

      <section className="grid gap-4 px-8 py-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <GitCommit className="h-4 w-4 text-muted-foreground" /> Pipeline
            </CardTitle>
            <CardDescription>End-to-end commit → deploy.</CardDescription>
          </CardHeader>
          <CardContent>
            {build.data ? (
              <PipelineSteps steps={pipelineFor(build.data)} />
            ) : (
              <Skeleton className="h-12 w-full" />
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Build metadata</CardTitle>
          </CardHeader>
          <CardContent>
            {build.data ? (
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <Meta label="Status">
                  <StatusBadge status={build.data.status} />
                </Meta>
                <Meta label="Source">{build.data.source}</Meta>
                <Meta label="Image tag">
                  <span className="font-mono text-xs">{build.data.image_tag ?? "—"}</span>
                </Meta>
                <Meta label="Image digest">
                  <span className="font-mono text-xs break-all">
                    {build.data.image_digest ?? "—"}
                  </span>
                </Meta>
                <Meta label="Started">{absTime(build.data.started_at)}</Meta>
                <Meta label="Finished">{absTime(build.data.finished_at)}</Meta>
                <Meta label="Duration">
                  {build.data.started_at && build.data.finished_at
                    ? formatDuration(
                        (new Date(build.data.finished_at).getTime() -
                          new Date(build.data.started_at).getTime()) /
                          1000,
                      )
                    : "—"}
                </Meta>
                <Meta label="Branch">
                  <span className="font-mono text-xs">{build.data.branch}</span>
                </Meta>
                {build.data.error && (
                  <div className="sm:col-span-2">
                    <Meta label="Error">
                      <pre className="whitespace-pre-wrap break-all rounded-md border border-destructive/40 bg-destructive/10 p-2 font-mono text-xs text-destructive">
                        {build.data.error}
                      </pre>
                    </Meta>
                  </div>
                )}
              </dl>
            ) : (
              <Skeleton className="h-40 w-full" />
            )}
          </CardContent>
        </Card>
      </section>

      <section className="px-8 pb-10">
        <LogStream buildId={id} />
      </section>
    </>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  );
}

function pipelineFor(run: BuildRun): PipelineStep[] {
  const status = run.status;
  const succeeded = (s: string) =>
    status === "succeeded" || status === "running" || status === "building" || status === "pushing"
      ? s
      : "pending";
  const buildState =
    status === "succeeded" || status === "pushing"
      ? "succeeded"
      : status === "building"
        ? "active"
        : status === "failed"
          ? "failed"
          : "pending";
  const pushState =
    status === "succeeded" ? "succeeded" : status === "pushing" ? "active" : "pending";
  const deployState = status === "succeeded" ? "active" : status === "failed" ? "skipped" : "pending";
  return [
    { key: "queue", label: "Queued", state: "succeeded" },
    {
      key: "clone",
      label: "Clone",
      state: status === "queued" ? "pending" : (succeeded("succeeded") as PipelineStep["state"]),
    },
    { key: "build", label: "Build", state: buildState },
    { key: "push", label: "Push", state: pushState },
    { key: "deploy", label: "Deploy", state: deployState },
  ];
}
