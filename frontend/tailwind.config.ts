import type { Config } from "tailwindcss";

// Design tokens: warm neutral dark surfaces with a single validated accent
// ramp (blue) and reserved status colors. Chart colors live in charts.tsx.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#0d0d0d", // page plane
        panel: "#1a1a19", // card surface
        raised: "#232322", // hover / inset surfaces
        edge: "rgba(255,255,255,0.08)", // hairline ring
        "edge-strong": "rgba(255,255,255,0.14)",
        ink: {
          DEFAULT: "#ffffff",
          secondary: "#c3c2b7",
          muted: "#898781",
        },
        accent: {
          300: "#6da7ec",
          400: "#5598e7",
          500: "#3987e5",
          600: "#256abf",
          700: "#1c5cab",
        },
        status: {
          good: "#0ca30c",
          warning: "#fab219",
          serious: "#ec835a",
          critical: "#d03b3b",
        },
        delta: {
          up: "#0ca30c",
          down: "#e66767",
        },
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.125rem",
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,0.4), 0 8px 24px -12px rgba(0,0,0,0.5)",
        "card-hover": "0 2px 4px rgba(0,0,0,0.4), 0 16px 40px -16px rgba(0,0,0,0.6)",
        glow: "0 0 0 1px rgba(57,135,229,0.35), 0 4px 24px -6px rgba(57,135,229,0.35)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        shimmer: {
          from: { backgroundPosition: "200% 0" },
          to: { backgroundPosition: "-200% 0" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.35s cubic-bezier(0.21, 1.02, 0.73, 1) both",
        "fade-in": "fade-in 0.25s ease-out both",
        shimmer: "shimmer 1.8s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
