import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      refetchOnWindowFocus: true,
      retry: (count, err: unknown) => {
        // 4xx — don't retry. Let the route handle it.
        if (err && typeof err === "object" && "status" in err) {
          const status = (err as { status?: number }).status ?? 0;
          if (status >= 400 && status < 500) return false;
        }
        return count < 2;
      },
    },
  },
});

export function QueryProvider({ children }: PropsWithChildren) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
