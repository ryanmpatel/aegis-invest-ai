// Minimal inline icon set (16/18px stroke icons, currentColor).
type IconProps = { className?: string };

const base = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function IconHome({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V21h14V9.5" />
      <path d="M10 21v-6h4v6" />
    </svg>
  );
}

export function IconChartPie({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <path d="M12 3a9 9 0 1 0 9 9h-9V3Z" />
      <path d="M15 3.5A9 9 0 0 1 20.5 9H15V3.5Z" />
    </svg>
  );
}

export function IconTarget({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconFlask({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <path d="M10 3v6L4.8 18.2A2 2 0 0 0 6.6 21h10.8a2 2 0 0 0 1.8-2.8L14 9V3" />
      <path d="M8.5 3h7" />
      <path d="M7.5 15h9" />
    </svg>
  );
}

export function IconPulse({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <path d="M3 12h4l2.5-7 4 14 2.5-7h5" />
    </svg>
  );
}

export function IconGear({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.2 13.6a7.6 7.6 0 0 0 0-3.2l2-1.5-2-3.4-2.4 1a7.7 7.7 0 0 0-2.7-1.6L13.7 2h-3.4l-.4 2.9a7.7 7.7 0 0 0-2.7 1.6l-2.4-1-2 3.4 2 1.5a7.6 7.6 0 0 0 0 3.2l-2 1.5 2 3.4 2.4-1a7.7 7.7 0 0 0 2.7 1.6l.4 2.9h3.4l.4-2.9a7.7 7.7 0 0 0 2.7-1.6l2.4 1 2-3.4-2-1.5Z" />
    </svg>
  );
}

export function IconShield({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <path d="M12 3 5 6v5c0 4.7 3 8.6 7 10 4-1.4 7-5.3 7-10V6l-7-3Z" />
      <path d="m9.2 12 2 2 3.6-4" />
    </svg>
  );
}

export function IconPower({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <path d="M12 3v8" />
      <path d="M6.3 6.5a8 8 0 1 0 11.4 0" />
    </svg>
  );
}

export function IconLogout({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <path d="M14 4h-8a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h8" />
      <path d="M10 12h10" />
      <path d="m17 8.5 3.5 3.5-3.5 3.5" />
    </svg>
  );
}
