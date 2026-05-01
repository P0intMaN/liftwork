import { useEffect, useRef, useState } from "react";
import { streamBuildLogs } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { UUID } from "@/lib/types";

export function LogStream({ buildId, className }: { buildId: UUID; className?: string }) {
  const [lines, setLines] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLines([]);
    setDone(false);
    setError(null);

    (async () => {
      try {
        for await (const evt of streamBuildLogs(buildId, controller.signal)) {
          if (evt.event === "end") {
            setDone(true);
            return;
          }
          if (evt.data != null && evt.data !== "") {
            setLines((prev) => [...prev, evt.data!]);
          }
        }
      } catch (e: unknown) {
        if ((e as { name?: string }).name === "AbortError") return;
        setError((e as Error).message);
      }
    })();

    return () => controller.abort();
  }, [buildId]);

  // Auto-scroll to bottom on new lines.
  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-[#0a0d14] p-4 font-mono text-xs",
        className,
      )}
    >
      <div className="mb-2 flex items-center justify-between text-[11px] uppercase tracking-wider text-muted-foreground">
        <span>build logs</span>
        <span>
          {done ? "complete" : error ? "error" : "live"}
          {!done && !error && (
            <span className="ml-2 inline-block h-1.5 w-1.5 animate-pulseDot rounded-full bg-info" />
          )}
        </span>
      </div>
      <div ref={containerRef} className="max-h-[28rem] overflow-y-auto">
        {error ? (
          <p className="log-line is-error">stream error: {error}</p>
        ) : lines.length === 0 && !done ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-3 w-full" />
            ))}
          </div>
        ) : (
          lines.map((line, i) => (
            <p
              key={i}
              className={cn(
                "log-line",
                /error|fail/i.test(line) && "is-error",
                /^\[(buildkit|deploy|build)\]/.test(line) && "is-meta",
              )}
            >
              {line}
            </p>
          ))
        )}
      </div>
    </div>
  );
}
