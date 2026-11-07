import { describe, expect, it } from 'vitest'

import { tokenStore } from '@/auth/tokens'
import { fakeApi, json } from '@/test/fakeApi'

import { api, ApiError, toApiError } from './client'

describe('authFetch', () => {
  it('sends the access token as a bearer header', async () => {
    tokenStore.set({ access: 'A1', refresh: 'R1' })
    const { calls } = fakeApi({ 'GET /auth/me': () => json({}) })
    await api.GET('/auth/me')
    expect(calls[0]?.auth).toBe('Bearer A1')
  })

  it('refreshes once for concurrent 401s, then retries each with the new token', async () => {
    tokenStore.set({ access: 'expired', refresh: 'R1' })
    const { calls } = fakeApi({
      'GET /auth/me': (req) =>
        req.headers.get('authorization') === 'Bearer A2' ? json({ ok: true }) : json({ detail: 'x' }, 401),
      'POST /auth/refresh': () => json({ access_token: 'A2', refresh_token: 'R2' }),
    })
    const results = await Promise.all([api.GET('/auth/me'), api.GET('/auth/me'), api.GET('/auth/me')])
    expect(results.every((r) => r.response.ok)).toBe(true)
    // Refresh tokens are single use with reuse detection: two refreshes would end the session.
    expect(calls.filter((c) => c.path === '/auth/refresh')).toHaveLength(1)
    expect(calls.find((c) => c.path === '/auth/refresh')?.body).toContain('"refresh_token":"R1"')
    expect(tokenStore.get()).toEqual({ access: 'A2', refresh: 'R2' })
  })

  it('ends the session when the refresh is refused', async () => {
    tokenStore.set({ access: 'expired', refresh: 'stolen' })
    fakeApi({
      'GET /auth/me': () => json({ detail: 'x' }, 401),
      'POST /auth/refresh': () => json({ detail: 'not authenticated' }, 401),
    })
    const r = await api.GET('/auth/me')
    expect(r.response.status).toBe(401)
    expect(tokenStore.get()).toBeNull()
  })

  it('never tries to refresh a failed sign-in', async () => {
    const { calls } = fakeApi({ 'POST /auth/token': () => json({ detail: 'no' }, 401) })
    tokenStore.set({ access: 'A1', refresh: 'R1' })
    await api.POST('/auth/token', {
      body: { username: 'u', password: 'p', scope: '' },
      bodySerializer: (b) => new URLSearchParams(b as Record<string, string>),
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
    })
    expect(calls.map((c) => c.path)).toEqual(['/auth/token'])
  })
})

describe('ApiError', () => {
  it('carries the short request reference and Retry-After', async () => {
    const response = json({ detail: 'too many requests; try again later' }, 429, { 'retry-after': '42' })
    const err = await toApiError(response, await response.clone().json())
    expect(err).toBeInstanceOf(ApiError)
    expect(err.reference).toBe('req_8f2c41')
    expect(err.retryAfterS).toBe(42)
    expect(err.message).toBe('too many requests; try again later')
  })
})
