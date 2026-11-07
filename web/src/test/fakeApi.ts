/** A tiny fake backend for tests: stub `fetch`, route by "METHOD /path", record calls. */
import { vi } from 'vitest'

export type Handler = (req: Request) => Response | Promise<Response>

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', 'x-request-id': '8f2c41aa-0000-4000-8000-000000000000', ...headers },
  })
}

export function fakeApi(routes: Record<string, Handler>) {
  const calls: { method: string; path: string; auth: string | null; body: string }[] = []
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = input instanceof Request ? input : new Request(input, init)
    const path = new URL(req.url).pathname
    const body = await req.clone().text()
    calls.push({ method: req.method, path, auth: req.headers.get('authorization'), body })
    // Like FastAPI: the OAuth2 password form must arrive form-encoded, or it's a 422.
    if (path === '/auth/token' && !req.headers.get('content-type')?.startsWith('application/x-www-form-urlencoded'))
      return json({ detail: [{ loc: ['body', 'username'], msg: 'Field required', type: 'missing' }] }, 422)
    const handler = routes[`${req.method} ${path}`]
    return handler ? handler(req) : json({ detail: `no fake for ${req.method} ${path}` }, 404)
  })
  vi.stubGlobal('fetch', fetch)
  return { calls, fetch }
}

export const ME = {
  coordinator: {
    username: 'hannah@demo.smartpbl',
    display_name: 'Hannah K.',
    role: 'coordinator',
    permissions: ['audit.read', 'note.create', 'note.read', 'review.decide', 'review.queue.read',
      'schedule.read', 'schedule.solve', 'workforce.read'],
  },
  carer: { username: 'joy@demo.smartpbl', display_name: 'Joy A.', role: 'carer', permissions: ['note.create'] },
} as const

export const TOKENS = { access_token: 'A1', refresh_token: 'R1', token_type: 'bearer', expires_in: 900, refresh_expires_in: 604800 }
