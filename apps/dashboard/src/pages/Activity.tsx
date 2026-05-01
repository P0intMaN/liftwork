import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ActivityFeed } from "@/components/ActivityFeed";

export default function ActivityPage() {
  const activity = useQuery({
    queryKey: ["activity-full"],
    queryFn: () => api.activity(200),
    refetchInterval: 5000,
  });
  return (
    <>
      <PageHeader title="Activity" subtitle="All recent build + deploy events. Refreshes every 5s." />
      <section className="px-8 py-6">
        <Card>
          <CardContent className="p-6">
            {activity.data ? (
              <ActivityFeed items={activity.data} />
            ) : (
              <div className="space-y-3">
                {Array.from({ length: 8 }).map((_, i) => (
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
