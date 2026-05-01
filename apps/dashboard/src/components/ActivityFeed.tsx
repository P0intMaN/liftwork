import { Link } from "react-router-dom";
import { GitCommit, Rocket } from "lucide-react";
import { StatusBadge } from "./StatusBadge";
import { relTime } from "@/lib/format";
import type { ActivityItem } from "@/lib/types";

export function ActivityFeed({ items }: { items: ActivityItem[] }) {
  if (!items.length) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border p-10 text-center">
        <p className="text-sm text-muted-foreground">no activity yet</p>
        <p className="mt-1 text-xs text-muted-foreground">
          build something — push to a connected repo or trigger a manual build
        </p>
      </div>
    );
  }
  return (
    <ol className="divide-y divide-border">
      {items.map((item) => (
        <li key={`${item.kind}-${item.id}`} className="flex items-center gap-4 py-3">
          <div className="grid h-8 w-8 place-items-center rounded-full border border-border bg-muted text-muted-foreground">
            {item.kind === "build" ? (
              <GitCommit className="h-4 w-4" />
            ) : (
              <Rocket className="h-4 w-4" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <Link
                to={
                  item.kind === "build"
                    ? `/builds/${item.id}`
                    : `/applications/${item.application_id}`
                }
                className="truncate text-sm font-medium hover:text-primary"
              >
                {item.application_slug ?? "unknown"}
              </Link>
              <StatusBadge status={item.status} />
            </div>
            <p className="truncate text-xs text-muted-foreground">{item.detail}</p>
          </div>
          <span className="shrink-0 text-xs text-muted-foreground">
            {relTime(item.created_at)}
          </span>
        </li>
      ))}
    </ol>
  );
}
