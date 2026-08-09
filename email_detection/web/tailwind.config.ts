import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // One colour per verdict, used consistently across the card, the
        // badge and the border so the verdict is readable at a glance.
        genuine: { bg: "#ecfdf5", fg: "#065f46", accent: "#059669" },
        tampered: { bg: "#fffbeb", fg: "#92400e", accent: "#d97706" },
        unverified: { bg: "#f8fafc", fg: "#334155", accent: "#64748b" },
        fraudulent: { bg: "#fef2f2", fg: "#991b1b", accent: "#dc2626" },
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "Segoe UI", "Inter", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
