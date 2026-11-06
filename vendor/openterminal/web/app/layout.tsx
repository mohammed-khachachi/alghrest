import type { Metadata } from "next";
import "./globals.css";
import Providers from "./providers";
import ResearchNotice from "../components/ResearchNotice";

export const metadata: Metadata = {
  title: "ALGHREST Research · OpenTerminal",
  description: "Public market research workspace for ALGHREST",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl" suppressHydrationWarning>
      <body style={{ display: "flex", flexDirection: "column", height: "100dvh" }}>
        <ResearchNotice />
        <div style={{ flex: 1, minHeight: 0 }}><Providers>{children}</Providers></div>
      </body>
    </html>
  );
}
