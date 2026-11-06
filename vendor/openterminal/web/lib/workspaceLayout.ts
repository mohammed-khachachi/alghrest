import type { LayoutItem } from "../store/terminal";

/** Narrow screens show a stack without replacing the user's saved desktop geometry. */
export function projectWorkspaceLayout(layout: LayoutItem[], narrow: boolean): LayoutItem[] {
  if (!narrow) return layout;

  let y = 0;
  return [...layout]
    .sort((a, b) => a.y - b.y || a.x - b.x)
    .map((item) => {
      const h = Math.max(item.h, 10);
      const projected = { ...item, x: 0, y, w: 12, h };
      y += h;
      return projected;
    });
}
