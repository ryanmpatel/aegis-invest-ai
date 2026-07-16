"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError, setCsrfToken } from "@/lib/api";
import { IconShield } from "@/components/icons";
import { Button, ErrorNote, Input } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<{ csrf_token: string }>("/api/auth/login", {
        username,
        password,
      });
      setCsrfToken(result.csrf_token);
      router.replace("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="page-enter w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-500 to-accent-700 text-white shadow-glow">
            <IconShield className="h-7 w-7" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            AegisInvest AI
          </h1>
          <p className="mt-1.5 text-sm text-ink-muted">
            Research, backtest, and paper-trade — safely.
          </p>
        </div>

        <div className="rounded-2xl border border-edge bg-panel/90 p-6 shadow-card backdrop-blur-sm">
          <form onSubmit={submit} className="space-y-3.5">
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.14em] text-ink-muted">
                Username
              </span>
              <Input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.14em] text-ink-muted">
                Password
              </span>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            {error && <ErrorNote message={error} />}
            <Button type="submit" className="mt-1 w-full" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs leading-relaxed text-ink-muted/70">
          Educational software. Paper trading only — live trading is permanently
          disabled. Nothing here is investment advice.
        </p>
      </div>
    </div>
  );
}
