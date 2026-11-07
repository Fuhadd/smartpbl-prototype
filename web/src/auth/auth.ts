import { createContext, use } from 'react'

import type { components } from '@/api/schema'

export type Me = components['schemas']['MeOut']
export type Role = Me['role']
export type Permission = Me['permissions'][number]

export type AuthState = {
  me: Me | null
  signIn: (username: string, password: string) => Promise<Me>
  signOut: () => Promise<void>
  /** UI hint only: the API enforces every permission itself (deny by default). */
  can: (permission: Permission) => boolean
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const ctx = use(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}

export const ROLE_LABEL: Record<Role, string> = {
  coordinator: 'Coordinator',
  manager: 'Care manager',
  carer: 'Carer',
}

export function initials(me: Me): string {
  const name = me.display_name || me.username
  const parts = name.replace(/[^\p{L}\s]/gu, ' ').trim().split(/\s+/)
  return parts
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}

export function firstName(me: Me): string {
  return (me.display_name || me.username).split(/[\s@.]/)[0] ?? ''
}
