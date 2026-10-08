export type DocumentRecord = { slug: string; path: string; ar: string; fr: string; summaryAr: string; summaryFr: string; markdown: string; hash: string; modified: string };
export type Evidence = { passed: number; skipped: number; coverage: number; date: string; scope: string };
export type Snapshot = { schema: number; generatedAt: string; evidence: Evidence | null; docs: DocumentRecord[] };
export const documents: Omit<DocumentRecord, "markdown" | "hash" | "modified">[];
export function extractEvidence(markdown: string): Evidence | null;
export function readRepositoryDocs(root: string): Promise<Snapshot>;

