import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { format, parseISO } from "date-fns";
import type { TimeseriesPoint } from "@/lib/types";

export function StackedActivityChart({
  data,
  successColor = "hsl(142 76% 47%)",
  failureColor = "hsl(0 75% 60%)",
}: {
  data: TimeseriesPoint[];
  successColor?: string;
  failureColor?: string;
}) {
  const padded = data.map((d) => ({
    ...d,
    label: format(parseISO(d.day), "MMM d"),
  }));
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={padded} margin={{ top: 10, right: 6, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id="successFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={successColor} stopOpacity={0.55} />
              <stop offset="95%" stopColor={successColor} stopOpacity={0} />
            </linearGradient>
            <linearGradient id="failureFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={failureColor} stopOpacity={0.55} />
              <stop offset="95%" stopColor={failureColor} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis dataKey="label" stroke="hsl(var(--muted-foreground))" fontSize={11} />
          <YAxis allowDecimals={false} stroke="hsl(var(--muted-foreground))" fontSize={11} />
          <Tooltip
            contentStyle={{
              background: "hsl(var(--card))",
              border: "1px solid hsl(var(--border))",
              borderRadius: 8,
              fontSize: 12,
            }}
          />
          <Area
            type="monotone"
            dataKey="succeeded"
            stackId="1"
            stroke={successColor}
            fill="url(#successFill)"
          />
          <Area
            type="monotone"
            dataKey="failed"
            stackId="1"
            stroke={failureColor}
            fill="url(#failureFill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
