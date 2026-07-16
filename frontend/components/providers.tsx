"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { IconShield } from "@/components/icons";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchInterval: 30_000, staleTime: 10_000 },
  },
});

function BootScreen({ message }: { message?: string }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-500 to-accent-700 text-white shadow-glow">
        <IconShield className="h-6 w-6" />
      </div>
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/15 border-t-accent-500" />
      {message && (
        <p className="max-w-sm text-center text-sm leading-relaxed text-ink-muted">
          {message}
        </p>
      )}
    </div>
  );
}

function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<"checking" | "ready" | "backend_down">(
    "checking",
  );
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (pathname === "/login") {
      setState("ready");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        // Hard 8s cap: a dead backend must never leave the page blank.
        const response = await fetch("/api/auth/me", {
          credentials: "include",
          signal: AbortSignal.timeout(8000),
        });
        if (cancelled) return;
        if (response.status === 401) {
          router.replace("/login");
          return;
        }
        if (response.status >= 502) {
          setState("backend_down");
          return;
        }
        setState("ready");
      } catch {
        if (!cancelled) setState("backend_down");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pathname, router, attempt]);

  // While the backend is down, retry every 10s (free-tier hosts wake slowly).
  useEffect(() => {
    if (state !== "backend_down") return;
    const timer = setTimeout(() => {
      setState("checking");
      setAttempt((a) => a + 1);
    }, 10_000);
    return () => clearTimeout(timer);
  }, [state, attempt]);

  if (state === "checking") return <BootScreen />;
  if (state === "backend_down") {
    return (
      <BootScreen
        message={
          "The backend isn't responding. If it was just deployed or has been " +
          "idle, it can take up to a minute to wake — retrying automatically."
        }
      />
    );
  }
  return <>{children}</>;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthGate>{children}</AuthGate>
    </QueryClientProvider>
  );
}
