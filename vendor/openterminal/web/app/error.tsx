"use client";
import { useLanguage, tr } from "../i18n";

import { useEffect } from "react";

// Route-level fallback for errors outside any widget (top bar, sidebar, layout grid).
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useLanguage();
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="p-4 flex flex-col gap-2 items-start">
      <span className="down">{tr("Terminal error: ")}{tr(error.message)}</span>
      <button onClick={reset} className="dim hover:text-[var(--amber)]">{tr("Retry")}</button>
    </div>
  );
}
