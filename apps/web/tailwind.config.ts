import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./tests/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        contour: {
          ink: "#07111f",
          mist: "#deecf4",
          tide: "#6dd3c7",
          sun: "#f0a357",
          rose: "#f47373",
          aurora: "#77baf8",
        },
      },
      boxShadow: {
        glow: "0 24px 80px rgba(11, 45, 78, 0.34)",
      },
    },
  },
  plugins: [],
};

export default config;
