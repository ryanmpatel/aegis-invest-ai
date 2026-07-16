import clsx from "clsx";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function Card({
  title,
  actions,
  children,
  className,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={clsx(
        "rounded-2xl border border-edge bg-panel/90 p-5 shadow-card",
        "backdrop-blur-sm transition-shadow duration-300 hover:shadow-card-hover",
        className,
      )}
    >
      {(title || actions) && (
        <header className="mb-4 flex items-center justify-between gap-2">
          {title && (
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-muted">
              {title}
            </h2>
          )}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "default" | "good" | "bad" | "warn";
}) {
  const toneClass = {
    default: "text-ink",
    good: "text-delta-up",
    bad: "text-delta-down",
    warn: "text-status-warning",
  }[tone];
  return (
    <div
      className={clsx(
        "group rounded-2xl border border-edge bg-panel/90 p-5 shadow-card",
        "transition-all duration-300 hover:border-edge-strong hover:shadow-card-hover",
      )}
    >
      <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-ink-muted">
        {label}
      </div>
      <div className={clsx("tnum mt-2 text-2xl font-semibold tracking-tight", toneClass)}>
        {value}
      </div>
      {sub && <div className="tnum mt-1.5 text-xs text-ink-muted">{sub}</div>}
    </div>
  );
}

const BADGE_TONES = {
  neutral: "bg-white/[0.06] text-ink-secondary border-edge",
  good: "bg-status-good/10 text-[#4ade4a] border-status-good/30",
  bad: "bg-status-critical/10 text-[#f28b8b] border-status-critical/35",
  warn: "bg-status-warning/10 text-status-warning border-status-warning/30",
  info: "bg-accent-500/10 text-accent-300 border-accent-500/30",
};

export function Badge({
  children,
  tone = "neutral",
  pulse = false,
}: {
  children: ReactNode;
  tone?: keyof typeof BADGE_TONES;
  pulse?: boolean;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5",
        "text-xs font-medium leading-5 transition-colors",
        BADGE_TONES[tone],
      )}
    >
      <span
        className={clsx(
          "h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-80",
          pulse && "animate-pulse",
        )}
        aria-hidden
      />
      {children}
    </span>
  );
}

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
}) {
  const variants = {
    primary:
      "bg-accent-600 text-white hover:bg-accent-500 active:bg-accent-700 shadow-[0_1px_2px_rgba(0,0,0,0.4),inset_0_1px_0_rgba(255,255,255,0.12)]",
    secondary:
      "bg-white/[0.07] text-ink hover:bg-white/[0.12] border border-edge active:bg-white/[0.05]",
    danger:
      "bg-status-critical text-white hover:bg-[#dd5050] active:bg-[#b83434] shadow-[0_1px_2px_rgba(0,0,0,0.4),inset_0_1px_0_rgba(255,255,255,0.12)]",
    ghost: "text-ink-secondary hover:bg-white/[0.06] hover:text-ink",
  };
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2",
        "text-sm font-medium transition-all duration-150",
        "active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={clsx(
        "w-full rounded-lg border border-edge bg-black/30 px-3.5 py-2 text-sm",
        "text-ink placeholder-ink-muted/70 transition-colors duration-150",
        "hover:border-edge-strong focus:border-accent-500 focus:outline-none",
        "focus:ring-2 focus:ring-accent-500/25",
        props.className,
      )}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={clsx(
        "w-full rounded-lg border border-edge bg-black/30 px-3.5 py-2 text-sm",
        "text-ink transition-colors duration-150 hover:border-edge-strong",
        "focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/25",
        props.className,
      )}
    />
  );
}

export function Table({
  headers,
  children,
}: {
  headers: string[];
  children: ReactNode;
}) {
  return (
    <div className="-mx-1 overflow-x-auto px-1">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-edge text-left text-[11px] uppercase tracking-[0.12em] text-ink-muted">
            {headers.map((h) => (
              <th key={h} className="px-2.5 py-2.5 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tnum divide-y divide-edge">{children}</tbody>
      </table>
    </div>
  );
}

export function Row({ children }: { children: ReactNode }) {
  return (
    <tr className="transition-colors duration-100 hover:bg-white/[0.03]">{children}</tr>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        "animate-shimmer rounded-lg",
        "bg-[linear-gradient(110deg,rgba(255,255,255,0.04)_40%,rgba(255,255,255,0.10)_50%,rgba(255,255,255,0.04)_60%)]",
        "bg-[length:200%_100%]",
        className,
      )}
    />
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-white/15 border-t-accent-500" />
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="animate-fade-up rounded-lg border border-status-critical/35 bg-status-critical/10 px-3.5 py-2.5 text-sm text-[#f2a1a1]"
    >
      {message}
    </div>
  );
}
