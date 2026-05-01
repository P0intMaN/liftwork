import { cn } from "@/lib/utils";
import type { BuildStatus, DeploymentStatus } from "@/lib/types";

type Status = BuildStatus | DeploymentStatus | string;

const PALETTE: Record<string, { dot: string; chip: string; label?: string }> = {
  // build
  queued:   { dot: "bg-muted-foreground", chip: "bg-muted text-muted-foreground" },
  running:  { dot: "bg-info animate-pulseDot", chip: "bg-info/15 text-info" },
  building: { dot: "bg-info animate-pulseDot", chip: "bg-info/15 text-info" },
  pushing:  { dot: "bg-info animate-pulseDot", chip: "bg-info/15 text-info" },
  succeeded:{ dot: "bg-success", chip: "bg-success/15 text-success" },
  failed:   { dot: "bg-destructive", chip: "bg-destructive/15 text-destructive" },
  cancelled:{ dot: "bg-muted-foreground", chip: "bg-muted text-muted-foreground" },
  // deploy
  pending:    { dot: "bg-muted-foreground", chip: "bg-muted text-muted-foreground" },
  applying:   { dot: "bg-info animate-pulseDot", chip: "bg-info/15 text-info" },
  rolling_out:{ dot: "bg-info animate-pulseDot", chip: "bg-info/15 text-info", label: "rolling out" },
  rolled_back:{ dot: "bg-warning", chip: "bg-warning/15 text-warning", label: "rolled back" },
  // cluster
  unknown:    { dot: "bg-muted-foreground", chip: "bg-muted text-muted-foreground" },
  healthy:    { dot: "bg-success", chip: "bg-success/15 text-success" },
  unreachable:{ dot: "bg-destructive", chip: "bg-destructive/15 text-destructive" },
};

export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  const p = PALETTE[status] ?? PALETTE.unknown!;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wider",
        p.chip,
        className,
      )}
    >
      <span className={cn("inline-block h-1.5 w-1.5 rounded-full", p.dot)} />
      {p.label ?? status}
    </span>
  );
}
