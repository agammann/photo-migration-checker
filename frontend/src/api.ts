let tokenRequest: Promise<string> | undefined;
const sessionKey = 'pmc-session';
const connectionMessage = 'Open the private link printed by the current app terminal.';

// Fragments stay out of HTTP requests. Remove the launch capability before
// rendering or making requests; retain it only for this tab's reloads.
const fragment = new URLSearchParams(window.location.hash.slice(1));
let sessionToken = fragment.get('session') ?? '';
if (fragment.has('session')) {
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
  try {
    if (/^[A-Za-z0-9_-]{43}$/.test(sessionToken)) sessionStorage.setItem(sessionKey, sessionToken);
    else sessionStorage.removeItem(sessionKey);
  } catch { /* This tab can still run in memory when browser storage is blocked. */ }
} else {
  try { sessionToken = sessionStorage.getItem(sessionKey) ?? ''; } catch { /* Use the current private launch link. */ }
}
if (!/^[A-Za-z0-9_-]{43}$/.test(sessionToken)) sessionToken = '';
// Opening a new launch link in an existing tab can be a fragment-only
// navigation. Reload that document so it consumes the new capability too.
window.addEventListener('hashchange', () => {
  if (new URLSearchParams(window.location.hash.slice(1)).has('session')) window.location.reload();
});

async function token() {
  if (!sessionToken) throw new Error(connectionMessage);
  tokenRequest ??= fetch('/api/bootstrap', { cache: 'no-store', headers: { 'X-PMC-Token': sessionToken }, redirect: 'error' })
    .then(async (response) => {
      if (response.status === 403) throw new Error(connectionMessage);
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
