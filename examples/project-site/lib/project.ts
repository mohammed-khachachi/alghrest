import "server-only";
import fs from "node:fs/promises";
import path from "node:path";
import { readRepositoryDocs, type Snapshot } from "./content-source.mjs";

export type ProjectSnapshot = Snapshot & { mode: "repository" | "snapshot" };
export async function getProject(): Promise<ProjectSnapshot> {
  try {
    return { ...await readRepositoryDocs(path.resolve(process.cwd(), "../..")), mode: "repository" };
  } catch {
    const snapshot = JSON.parse(await fs.readFile(path.join(process.cwd(), "content/docs.json"), "utf8")) as Snapshot;
    return { ...snapshot, mode: "snapshot" };
  }
}
export async function getSummary() {
  const project = await getProject();
  return { ...project, docs: project.docs.map(doc => ({ slug:doc.slug, ar:doc.ar, fr:doc.fr, summaryAr:doc.summaryAr, summaryFr:doc.summaryFr, path:doc.path, hash:doc.hash, modified:doc.modified })) };
}
export type ProjectSummary = Awaited<ReturnType<typeof getSummary>>;
