import type { Config } from "tailwindcss";

/**
 * GroundCite "mission control" theme (spec §2.2).
 *
 * These tokens are the single source for the visual theme. JetBrains Mono is the
 * signature detail — every clause ID, standard code, and score renders in mono.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Surfaces
        background: "#0B0E14", // near-black
        surface: "#131822",
        border: "#232B3A",
        // Text
        text: "#E6EAF2",
        // Accents / status
        grounded: "#2FBF71", // GROUNDED chip (green)
        abstained: "#F5A623", // ABSTAINED chip (amber)
        link: "#4CC3FF", // cyan
      },
      fontFamily: {
        // Inter for UI, JetBrains Mono for clause IDs / codes / scores (spec §2.2).
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
