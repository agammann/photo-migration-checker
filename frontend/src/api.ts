let tokenRequest: Promise<string> | undefined;

async function token() {
  tokenRequest ??= fetch('/api/bootstrap', { cache: 'no-store' })
    .then(async (response) => {
      if (!response.ok) throw new Error('The local app is unavailable. Check that its server is running.');
      return (await response.json() as { token: string }).token;
    }).catch((error: unknown) => {
      tokenRequest = undefined;
      throw error;
    });
  return tokenRequest;
}

export async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'X-PMC-Token': await token(), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store',
    redirect: 'error',
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({})) as { detail?: unknown };
    throw new Error(typeof data.detail === 'string' ? data.detail : `The local request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export async function exportReport(id: string, format: 'json' | 'html') {
  const response = await fetch(`/api/scans/${encodeURIComponent(id)}/export?format=${format}`, {
    headers: { 'X-PMC-Token': await token() }, cache: 'no-store', redirect: 'error',
  });
  if (!response.ok) throw new Error('The report could not be exported. Open this scan and try again.');
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `photo-migration-${id.slice(0, 8)}.${format}`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
