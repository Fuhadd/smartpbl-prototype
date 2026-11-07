import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api, toApiError } from '@/api/client'

import { AuthContext, type Me, type Permission } from './auth'
import { tokenStore } from './tokens'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)

  // A failed refresh clears the tokens: drop the user so routes send them to sign-in.
  useEffect(() => tokenStore.subscribe((tokens) => tokens === null && setMe(null)), [])

  const signIn = useCallback(async (username: string, password: string) => {
    const token = await api.POST('/auth/token', {
      body: { username, password, grant_type: 'password', scope: '' },
      bodySerializer: (body) => new URLSearchParams(body as Record<string, string>),
      // openapi-fetch keeps its JSON default unless told: the OAuth2 form must say so.
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
    })
    if (!token.data) throw await toApiError(token.response, token.error)
    tokenStore.set({ access: token.data.access_token, refresh: token.data.refresh_token })
    const who = await api.GET('/auth/me')
    if (!who.data) {
      tokenStore.set(null)
      throw await toApiError(who.response, who.error)
    }
    setMe(who.data)
    return who.data
  }, [])

  const signOut = useCallback(async () => {
    const refresh = tokenStore.get()?.refresh
    tokenStore.set(null)
    setMe(null)
    if (refresh) await api.POST('/auth/logout', { body: { refresh_token: refresh } }).catch(() => undefined)
  }, [])

  const can = useCallback((permission: Permission) => me?.permissions.includes(permission) ?? false, [me])

  const value = useMemo(() => ({ me, signIn, signOut, can }), [me, signIn, signOut, can])
  return <AuthContext value={value}>{children}</AuthContext>
}
