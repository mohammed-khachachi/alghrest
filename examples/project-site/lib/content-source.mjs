import { readFile, stat } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";

export const documents = [
  { slug: "overview", path: "README.md", ar: "نظرة عامة", fr: "Vue d’ensemble", summaryAr: "المشروع الحالي، التشغيل، الأدلة والحدود.", summaryFr: "État, démarrage, preuves et limites." },
  { slug: "dashboard", path: "dashboard/README.md", ar: "الواجهة والمساعد", fr: "Interface et assistant", summaryAr: "المسارات والاتصالات وفصل الوصول.", summaryFr: "Routes, connexions et accès séparés." },
  { slug: "research", path: "research/README.md", ar: "البحث والتجارب", fr: "Recherche", summaryAr: "البحث المستقل وحدود البيانات المصطنعة.", summaryFr: "Études indépendantes et données synthétiques." },
  { slug: "hmm", path: "research/hmm_trading/README.md", ar: "دراسة HMM", fr: "Étude HMM", summaryAr: "التنزيل والبديل المصطنع والمخرجات.", summaryFr: "Chargement, repli synthétique et résultats." },
  { slug: "models", path: "artifacts/README.md", ar: "النماذج والأدلة", fr: "Modèles et preuves", summaryAr: "الأصول المضمنة وما لم يُعتمد بعد.", summaryFr: "Actifs conservés et limites de validation." },
  { slug: "documentation", path: "docs/README.md", ar: "خريطة التوثيق", fr: "Documentation", summaryAr: "المعمارية والسياسة وخطة التطوير.", summaryFr: "Architecture, politique et développement." },
];

export function extractEvidence(markdown) {
  const match = markdown.match(/passed \*\*([\d,]+) tests\*\*, with\s+\*\*(\d+) external-service opt-ins skipped\*\* and \*\*([\d.]+)%\*\*/);
  const date = markdown.match(/snapshot on (\d{4}-\d{2}-\d{2}) passed/);
  if (!match || !date) return null;
  const evidence = { passed: Number(match[1].replaceAll(",", "")), skipped: Number(match[2]), coverage: Number(match[3]), date: date[1], scope: "local-upload-snapshot" };
  if (![evidence.passed, evidence.skipped, evidence.coverage].every(Number.isFinite) || evidence.passed < 0 || evidence.skipped < 0 || evidence.coverage < 0 || evidence.coverage > 100) return null;
  return evidence;
}

export async function readRepositoryDocs(root) {
  const docs = await Promise.all(documents.map(async doc => {
    // Runtime allowlist only. Never trace the surrounding private repository into a deployment.
    const filename = path.join(/* turbopackIgnore: true */ root, doc.path);
    const [markdown, info] = await Promise.all([readFile(/* turbopackIgnore: true */ filename, "utf8"), stat(/* turbopackIgnore: true */ filename)]);
    return { ...doc, markdown, hash: createHash("sha256").update(markdown).digest("hex"), modified: info.mtime.toISOString() };
  }));
  return { schema: 1, generatedAt: new Date().toISOString(), evidence: extractEvidence(docs[0].markdown), docs };
}
