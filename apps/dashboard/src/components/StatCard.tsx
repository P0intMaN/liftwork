import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type TrendTone = "muted" | "positive" | "warning" | "danger";

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  trend,
  className,
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon?: LucideIcon;
  trend?: { value: string; tone?: TrendTone };
  className?: string;
}) {
  const toneClass: Record<TrendTone, string> = {
    muted: "text-muted-foreground",
    positive: "text-success",
    warning: "text-warning",
    danger: "text-destructive",
  };
  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary/40",
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
      </div>
      <div className="mt-2 flex items-baseline gap-3">
        <span className="text-3xl font-semibold tracking-tight tabular-nums">{value}</span>
        {trend && (
          <span className={cn("text-xs font-medium tabular-nums", toneClass[trend.tone ?? "muted"])}>
            {trend.value}
          </span>
        )}
      </div>
      {hint && <p className="mt-2 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
