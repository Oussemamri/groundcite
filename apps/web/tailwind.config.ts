import type { Config } from "tailwindcss";

/**
 * GroundCite "mission control" theme (spec §2.2) — applies to `/library`,
 * `/evals`, `/documents/[slug]`. JetBrains Mono is the signature detail —
 * every clause ID, standard code, and score renders in mono.
 *
 * The `chat` color set (spec §2.2.1, Week 6) is a SEPARATE, distinctly-
 * prefixed palette for `/ask` only — a deliberate, owner-directed pivot for
 * that one page, additive here so the tokens above stay untouched for every
 * other page.
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
        // /ask chat theme (spec §2.2.1, Week 6) — warm "paper" palette.
        chat: {
          bg: "#F0EEE6",
          panel: "#E9E6DC",
          card: "#FDFCF8",
          composer: "#FFFFFF",
          bubble: "#E7E0CF",
          ink: "#2B2A24",
          line: "#DCD8CA",
          "line-dim": "#CFC9B9",
          "line-card": "#E2DED0",
          "line-user": "#E0D9C7",
          accent: {
            DEFAULT: "#C15F3C",
            hover: "#A94F32",
          },
          grounded: "#1C7A4D",
          abstained: "#A16207",
        },
      },
      fontFamily: {
        // Inter for UI, JetBrains Mono for clause IDs / codes / scores (spec §2.2).
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
        // /ask chat theme prose (spec §2.2.1, Week 6) — Source Serif 4.
        serif: ["var(--font-source-serif)", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};

export default config;
