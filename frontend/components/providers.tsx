"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchInterval: 30_000, staleTime: 10_000 },
  },
});

function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (pathname === "/login") {
      setChecked(true);
      return;
    }
    api
      .get("/api/auth/me")
      .then(() => setChecked(true))
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 401) {
          router.replace("/login");
        } else {
          setChecked(true); // backend down: let pages render their own errors
        }
      });
  }, [pathname, router]);

  if (!checked) return null;
  return <>{children}</>;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthGate>{children}</AuthGate>
    </QueryClientProvider>
  );
}
