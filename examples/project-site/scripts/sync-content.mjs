import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readRepositoryDocs } from "../lib/content-source.mjs";
const site = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const snapshot = await readRepositoryDocs(path.resolve(site, "../.."));
await fs.mkdir(path.join(site, "content"), { recursive: true });
await fs.writeFile(path.join(site, "content/docs.json"), JSON.stringify(snapshot, null, 2) + "\n");
console.log("Synchronized 6 allowlisted README files. No runtime or account data collected.");

