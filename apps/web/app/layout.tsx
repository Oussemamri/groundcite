import type { Metadata } from "next";
import { JetBrains_Mono, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

// The two faces of the warm "paper" theme (spec §2.2): Source Serif 4 for
// all prose, JetBrains Mono for every clause ID / code / score. Self-hosted
// at build time via next/font/google — no runtime Google Fonts request.
const sourceSerif = Source_Serif_4({ subsets: ["latin"], variable: "--font-source-serif" });
const jetbrainsMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains-mono" });

export const metadata: Metadata = {
  title: "GroundCite",
  description: "Grounded Q&A over aerospace & engineering standards — with exact clause citations.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sourceSerif.variable} ${jetbrainsMono.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
