import { getSummary } from "@/lib/project";
export const dynamic = "force-dynamic";
export async function GET() {
  return Response.json(await getSummary(), { headers: { "Cache-Control": "no-store" } });
}

