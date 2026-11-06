"use client";
import { useLanguage, tr, languageDirection } from "../i18n";

import "./globals.css";

// Last-resort fallback when the root layout itself throws; replaces <html>/<body>.
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useLanguage();
  return (
    <html lang={languageDirection() === "rtl" ? "ar" : "en"} dir={languageDirection()}>
      <body>
        <div className="p-4 flex flex-col gap-2 items-start">
          <span className="down">{tr("Terminal error: ")}{tr(error.message)}</span>
          <button onClick={reset} className="dim hover:text-[var(--amber)]">{tr("Retry")}</button>
        </div>
      </body>
    </html>
  );
}
