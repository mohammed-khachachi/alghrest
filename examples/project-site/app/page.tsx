import { getSummary } from "@/lib/project";
import { ProjectSite } from "@/components/project-site";
export const dynamic = "force-dynamic";
export default async function Home({ searchParams }: { searchParams: Promise<{ lang?: string }> }) {
  const [project, params] = await Promise.all([getSummary(), searchParams]);
  return <ProjectSite initialProject={project} initialLanguage={params.lang === "fr" ? "fr" : "ar"} />;
}

