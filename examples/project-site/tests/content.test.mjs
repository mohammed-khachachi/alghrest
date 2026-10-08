import test from "node:test";
import assert from "node:assert/strict";
import { extractEvidence, documents } from "../lib/content-source.mjs";
test("local test evidence preserves skipped tests, period and coverage", () => {
 const value = extractEvidence("snapshot on 2026-10-06 passed **2,112 tests**, with\n**53 external-service opt-ins skipped** and **82.16%** combined coverage");
 assert.deepEqual(value, { passed:2112, skipped:53, coverage:82.16, date:"2026-10-06", scope:"local-upload-snapshot" });
});
test("missing or changed evidence remains unknown rather than inventing zero or success", () => {
 for (const text of ["", "all tests passed", "passed **10 tests**", "snapshot on 2026-10-06 passed **2 tests**, with **1 external-service opt-ins skipped** and **101%** coverage"]) assert.equal(extractEvidence(text), null);
});
test("document collection is fixed to README files; no secret, logs or account stores", () => {
 assert.equal(new Set(documents.map(d=>d.slug)).size, documents.length);
 for (const doc of documents) {
  assert.ok(doc.path.endsWith("README.md"));
  assert.ok(!doc.path.includes("..") && !doc.path.includes(".env") && !doc.path.includes(".secrets"));
 }
});

