import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0b1020",
        panel: "#111729",
        line: "#1f2740",
        ink: "#e6e8f0",
        muted: "#8a93b2",
        accent: "#4f8cff",
        crit: "#ff5560",
        high: "#ff944d",
        med: "#ffcb47",
        low: "#48d699",
      },
    },
  },
  plugins: [],
};

export default config;
