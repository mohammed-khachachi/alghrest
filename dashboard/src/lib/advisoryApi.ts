import { accessHeaders } from '@/lib/access';
export async function advisoryApi<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/assistant-api/${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', 'X-Advisory-Client': 'dashboard', ...accessHeaders('advisory') },
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({})) as { detail?: unknown };
    throw new Error(typeof data.detail === 'string' ? data.detail : 'تعذر إكمال الطلب. تحقق من البيانات وخدمة المساعد.');
  }
  return response.json() as Promise<T>;
}
