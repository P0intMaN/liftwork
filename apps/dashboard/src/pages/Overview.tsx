import { useQuery } from "@tanstack/react-query";
import { Boxes, GitBranch, Rocket, Server, Timer, TrendingUp } from "lucide-react";
import { api } from "@/lib/api";
import { formatDuration, pct } from "@/lib/format";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatCard } from "@/components/StatCard";
import { StackedActivityChart } from "@/components/BuildsChart";
import { ActivityFeed } from "@/components/ActivityFeed";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function OverviewPage() {
  const summary = useQuery({ queryKey: ["summary"], queryFn: () => api.summary(30) });
  const buildsTs = useQuery({ queryKey: ["builds-ts"], queryFn: () => api.buildsTimeseries(30) });
  const deploysTs = useQuery({ queryKey: ["deploys-ts"], queryFn: () => api.deploysTimeseries(30) });
  const activity = useQuery({ queryKey: ["activity"], queryFn: () => api.activity(20), refetchInterval: 5000 });

  const s = summary.data;

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle="Last 30 days · build & deploy pipeline health, live."
      />
      <section className="grid gap-4 px-8 py-6 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Builds"
          icon={GitBranch}
          value={s?.builds.total ?? "—"}
          hint={s ? `${pct(s.builds.succeeded, s.builds.total)} success rate` : undefined}
          trend={
            s
              ? {
                  value: `${s.builds.in_flight} in flight`,
                  positive: s.builds.in_flight > 0,
                }
              : undefined
          }
        />
        <StatCard
          label="Avg build time"
          icon={Timer}
          value={s ? formatDuration(s.builds.avg_duration_seconds) : "—"}
          hint="across succeeded + failed runs"
        />
        <StatCard
          label="Deploys"
          icon={Rocket}
          value={s?.deploys.total ?? "—"}
          hint={s ? `${pct(s.deploys.succeeded, s.deploys.total)} rolled out` : undefined}
        />
        <StatCard
          label="Footprint"
          icon={Boxes}
          value={s ? `${s.applications}` : "—"}
          hint={s ? `apps · ${s.clusters} clusters connected` : undefined}
        />
      </section>

      <section className="grid gap-4 px-8 pb-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
              Builds per day
            </CardTitle>
            <CardDescription>Stacked succeeded vs failed, last 30 days.</CardDescription>
          </CardHeader>
          <CardContent>
            {buildsTs.data ? (
              <StackedActivityChart data={buildsTs.data} />
            ) : (
              <Skeleton className="h-64 w-full" />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Server className="h-4 w-4 text-muted-foreground" />
              Deploys per day
            </CardTitle>
            <CardDescription>Same window, k8s rollouts.</CardDescription>
          </CardHeader>
          <CardContent>
            {deploysTs.data ? (
              <StackedActivityChart
                data={deploysTs.data}
                successColor="hsl(213 94% 68%)"
                failureColor="hsl(35 92% 56%)"
              />
            ) : (
              <Skeleton className="h-64 w-full" />
            )}
          </CardContent>
        </Card>
      </section>

      <section className="px-8 pb-10">
        <Card>
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
            <CardDescription>Auto-refreshes every 5s.</CardDescription>
          </CardHeader>
          <CardContent>
            {activity.data ? (
              <ActivityFeed items={activity.data} />
            ) : (
              <div className="space-y-3">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </>
  );
}
