import type { Config } from "tailwindcss";

/**
 * GroundCite warm "paper" theme (spec §2.2) — the single, site-wide token
 * system, from the owner-supplied Claude design handoff
 * (design_handoff_chat_redesign/). One semantic palette, no per-page
 * namespaces: every page reads from these tokens, so the design cannot
 * drift page-by-page again.
 *
 * JetBrains Mono is still the signature detail — every clause ID, standard
 * code, and score renders in mono (spec §2.2, unchanged through every
 * theme iteration).
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Surfaces
        paper: "#F0EEE6", // page background
        panel: "#E9E6DC", // sidebars, nav, footers
        card: "#FDFCF8", // content cards, table surfaces
        composer: "#FFFFFF", // input fields
        bubble: "#E7E0CF", // user chat bubbles
        header: "rgba(250,249,245,0.92)", // sticky headers, paired with backdrop-blur
        // Text
        ink: "#2B2A24",
        // Hairlines
        line: {
          DEFAULT: "#DCD8CA",
          dim: "#CFC9B9",
          card: "#E2DED0",
          user: "#E0D9C7",
        },
        // Accents / status
        accent: {
          DEFAULT: "#C15F3C",
          hover: "#A94F32",
        },
        grounded: "#1C7A4D", // GROUNDED chip (green)
        abstained: "#A16207", // ABSTAINED chip (ochre — amber-family, never red)
      },
      fontFamily: {
        // Source Serif 4 for all prose; JetBrains Mono for clause IDs /
        // codes / scores / metadata (spec §2.2). No sans face — the design
        // uses exactly these two.
        serif: ["var(--font-source-serif)", "Georgia", "serif"],
        mono: ["var(--font-jetbrains-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
