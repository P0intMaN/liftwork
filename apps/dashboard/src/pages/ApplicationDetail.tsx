import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams, Link } from "react-router-dom";
import { ArrowLeft, GitBranch, Play, Rocket } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { absTime, formatDuration, relTime, shortSha } from "@/lib/format";

export default function ApplicationDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const app = useQuery({ queryKey: ["app", id], queryFn: () => api.getApplication(id) });
  const builds = useQuery({
    queryKey: ["app", id, "builds"],
    queryFn: () => api.listBuilds(id),
    refetchInterval: 5000,
  });
  const deploys = useQuery({
    queryKey: ["app", id, "deployments"],
    queryFn: () => api.listDeployments(id),
    refetchInterval: 5000,
  });

  const trigger = useMutation({
    mutationFn: () => api.triggerBuild(id),
    onSuccess: ({ build_id }) => {
      toast.success("build queued");
      queryClient.invalidateQueries({ queryKey: ["app", id, "builds"] });
      navigate(`/builds/${build_id}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <>
      <PageHeader
        title={app.data?.display_name ?? "—"}
        subtitle={
          app.data
            ? `${app.data.repo_owner}/${app.data.repo_name} · ${app.data.default_branch} → ${app.data.namespace}`
            : ""
        }
        actions={
          <>
            <Button variant="ghost" asChild>
              <Link to="/applications">
                <ArrowLeft className="h-4 w-4" /> All apps
              </Link>
            </Button>
            <Button onClick={() => trigger.mutate()} disabled={trigger.isPending}>
              <Play className="h-4 w-4" /> Trigger build
            </Button>
          </>
        }
      />

      <section className="grid gap-4 px-8 py-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <GitBranch className="h-4 w-4 text-muted-foreground" />
              Recent builds
            </CardTitle>
            <CardDescription>Click a row to follow live logs.</CardDescription>
          </CardHeader>
          <CardContent>
            {builds.isLoading ? (
              <Skeleton className="h-40 w-full" />
            ) : builds.data?.length ? (
              <ol className="divide-y divide-border">
                {builds.data.map((b) => (
                  <li key={b.id}>
                    <Link
                      to={`/builds/${b.id}`}
                      className="flex items-center gap-3 py-3 hover:bg-secondary/50 -mx-2 px-2 rounded-md transition-colors"
                    >
                      <StatusBadge status={b.status} />
                      <div className="flex-1 min-w-0">
                        <p className="truncate text-sm font-medium">
                          {b.commit_message ?? `commit ${shortSha(b.commit_sha)}`}
                        </p>
                        <p className="font-mono text-xs text-muted-foreground">
                          {b.branch} · {shortSha(b.commit_sha)} · source:{b.source}
                        </p>
                      </div>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {b.started_at && b.finished_at
                          ? formatDuration(
                              (new Date(b.finished_at).getTime() - new Date(b.started_at).getTime()) /
                                1000,
                            )
                          : relTime(b.created_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="py-6 text-center text-sm text-muted-foreground">
                no builds yet — push to {app.data?.default_branch ?? "main"} or hit Trigger build
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Rocket className="h-4 w-4 text-muted-foreground" />
              Deployments
            </CardTitle>
            <CardDescription>Per-revision rollouts.</CardDescription>
          </CardHeader>
          <CardContent>
            {deploys.isLoading ? (
              <Skeleton className="h-40 w-full" />
            ) : deploys.data?.length ? (
              <ol className="space-y-2">
                {deploys.data.map((d) => (
                  <li
                    key={d.id}
                    className="flex items-center justify-between rounded-md border border-border p-3"
                  >
                    <div>
                      <p className="text-sm font-medium">rev {d.revision}</p>
                      <p className="font-mono text-[11px] text-muted-foreground">
                        {d.image_tag}
                      </p>
                      <p className="text-[11px] text-muted-foreground">
                        {absTime(d.finished_at ?? d.created_at)}
                      </p>
                    </div>
                    <StatusBadge status={d.status} />
                  </li>
                ))}
              </ol>
            ) : (
              <p className="py-6 text-center text-sm text-muted-foreground">no rollouts yet</p>
            )}
          </CardContent>
        </Card>
      </section>
    </>
  );
}
