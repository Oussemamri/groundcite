import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const jetbrainsMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains-mono" });
// Week 6: /ask's chat theme (spec §2.2.1) — self-hosted at build time via
// next/font/google, same pattern as the two fonts above (not a runtime
// Google Fonts request). Declared here so its CSS variable is available
// globally; the `font-serif` Tailwind utility is only ever applied inside
// the /ask chat components.
const sourceSerif = Source_Serif_4({ subsets: ["latin"], variable: "--font-source-serif" });

export const metadata: Metadata = {
  title: "GroundCite",
  description: "Grounded Q&A over aerospace & engineering standards — with exact clause citations.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable} ${sourceSerif.variable}`}
    >
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
