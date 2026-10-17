import type { Metadata } from "next";
import "./globals.css";
import Providers from "./providers";

export const metadata: Metadata = {
  title: "ALGHREST Research · OpenTerminal",
  description: "Public market research workspace for ALGHREST",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ display: "flex", flexDirection: "column", height: "100dvh" }}>
        <div role="status" style={{ padding: "8px 12px", background: "#241b08", color: "#fcd34d", fontSize: 12, flexShrink: 0 }}>
          ALGHREST Research · Public prices may be delayed or indicative. Portfolio entries are a separate manual journal.
          {" "}<a href="http://127.0.0.1:5173/assistant" target="_top" style={{ textDecoration: "underline" }}>Return to ALGHREST</a>
        </div>
        <div style={{ flex: 1, minHeight: 0 }}><Providers>{children}</Providers></div>
      </body>
    </html>
  );
}
