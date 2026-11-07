/**
 * Typed API client. `paths` is generated from the backend's OpenAPI schema
 * (`npm run gen:api`), so a renamed field or route is a compile error, not a runtime bug.
 */
import createClient from 'openapi-fetch'

import { tokenStore } from '@/auth/tokens'

import type { paths } from './schema'

export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

/** A failed API call, with the server's request id for support ("Reference: req_…"). */
export class ApiError extends Error {
  readonly status: number
  readonly requestId: string | null
  readonly retryAfterS: number | null

  constructor(status: number, detail: string, requestId: string | null, retryAfterS: number | null) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.requestId = requestId
    this.retryAfterS = retryAfterS
  }

  /** The short reference shown to users: "req_" + the first 6 hex digits of the id. */
  get reference(): string | null {
    return this.requestId ? `req_${this.requestId.replaceAll('-', '').slice(0, 6)}` : null
  }
}

export async function toApiError(response: Response, error: unknown): Promise<ApiError> {
  const detail =
    typeof error === 'object' && error !== null && 'detail' in error && typeof error.detail === 'string'
      ? error.detail
      : response.statusText || `HTTP ${response.status}`
  const retry = response.headers.get('retry-after')
  return new ApiError(response.status, detail, response.headers.get('x-request-id'), retry ? Number(retry) : null)
}

// --- authenticated fetch ---------------------------------------------------------------

const NO_REFRESH = ['/auth/token', '/auth/refresh', '/auth/logout']
let refreshing: Promise<boolean> | null = null

/**
 * Exchange the refresh token once, shared by every request that hit 401 at the same time.
 * Refresh tokens are single use with reuse detection (ADR-025), so two parallel refreshes
 * with the same token would look like theft and revoke the whole session.
 */
function refreshOnce(): Promise<boolean> {
  refreshing ??= (async () => {
    const refresh = tokenStore.get()?.refresh
    if (!refresh) return false
    try {
      const response = await globalThis.fetch(`${API_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      })
      if (!response.ok) return false
      const body = (await response.json()) as { access_token: string; refresh_token: string }
      tokenStore.set({ access: body.access_token, refresh: body.refresh_token })
      return true
    } catch {
      return false
    }
  })().then((ok) => {
    if (!ok) tokenStore.set(null) // session over: the app returns to sign-in
    refreshing = null
    return ok
  })
  return refreshing
}

function withBearer(request: Request): Request {
  const access = tokenStore.get()?.access
  if (!access) return request
  const headers = new Headers(request.headers)
  headers.set('authorization', `Bearer ${access}`)
  return new Request(request, { headers })
}

export async function authFetch(input: Request): Promise<Response> {
  const retry = input.clone() // a body can be read once; keep a copy for the retry
  const response = await globalThis.fetch(withBearer(input))
  const path = new URL(input.url).pathname
  if (response.status !== 401 || NO_REFRESH.includes(path) || !tokenStore.get()) return response
  return (await refreshOnce()) ? globalThis.fetch(withBearer(retry)) : response
}

export const api = createClient<paths>({ baseUrl: API_URL, fetch: authFetch })
