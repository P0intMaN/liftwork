import { Check, CircleDashed, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";

type StepState = "pending" | "active" | "succeeded" | "failed" | "skipped";

export interface PipelineStep {
  key: string;
  label: string;
  state: StepState;
}

export function PipelineSteps({ steps }: { steps: PipelineStep[] }) {
  return (
    <ol className="flex w-full items-stretch gap-2 overflow-x-auto">
      {steps.map((step, idx) => {
        const last = idx === steps.length - 1;
        return (
          <li key={step.key} className="flex flex-1 items-center gap-2">
            <div
              className={cn(
                "flex flex-1 items-center gap-3 rounded-lg border px-3 py-2 transition-colors",
                step.state === "active" && "border-info bg-info/5",
                step.state === "succeeded" && "border-success/40 bg-success/5",
                step.state === "failed" && "border-destructive/40 bg-destructive/5",
                step.state === "skipped" && "border-dashed border-muted-foreground/30 opacity-60",
                step.state === "pending" && "border-border",
              )}
            >
              <StepIcon state={step.state} />
              <span className="text-xs font-medium">{step.label}</span>
            </div>
            {!last && (
              <span
                className={cn(
                  "h-px w-6 bg-border transition-colors",
                  step.state === "succeeded" && "bg-success/60",
                  step.state === "failed" && "bg-destructive/60",
                )}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}

function StepIcon({ state }: { state: StepState }) {
  switch (state) {
    case "succeeded":
      return <Check className="h-4 w-4 text-success" />;
    case "failed":
      return <X className="h-4 w-4 text-destructive" />;
    case "active":
      return <Loader2 className="h-4 w-4 animate-spin text-info" />;
    default:
      return <CircleDashed className="h-4 w-4 text-muted-foreground" />;
  }
}
