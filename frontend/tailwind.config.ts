import type { Config } from "tailwindcss";

// VibeTrack design tokens.
// Deep Slate (background), Electric Cyan (live / healthy), Warning Orange (compromised).
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        slate: {
          950: "#06080C",
          900: "#0B0F16",
          850: "#10151E",
          800: "#161C26",
          700: "#1E2632",
          500: "#5B6776",
          400: "#7A8493",
          200: "#C7CDD6",
          100: "#E6E9EF",
        },
        cyan: {
          DEFAULT: "#22D3EE",
          dim: "#0FB6CE",
          glow: "rgba(34,211,238,0.18)",
        },
        warn: {
          DEFAULT: "#FB923C",
          dim: "#C45A0F",
          glow: "rgba(251,146,60,0.18)",
        },
      },
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'SF Pro Text', 'Inter', 'sans-serif'],
        mono: ['ui-monospace', 'SF Mono', 'Menlo', 'monospace'],
      },
      letterSpacing: {
        tightest: "-0.04em",
      },
      boxShadow: {
        glow: "0 0 40px -10px rgba(34,211,238,0.45)",
        warn: "0 0 40px -10px rgba(251,146,60,0.55)",
        panic: "0 0 80px -10px rgba(239,68,68,0.65)",
      },
    },
  },
  plugins: [],
};
export default config;
