import { useEffect, useState, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'

import { useAuth } from '@/auth/auth'
import { AccessDenied } from '@/components/states/States'
import { CARER_APP_URL } from '@/config'

import { PageHeader } from './AppShell'
import { page, type PageKey } from './pages'

/** Signed-out users go to sign-in, and come back to where they were afterwards. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { me } = useAuth()
  const location = useLocation()
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}

const ROLE_WORD = { coordinator: 'coordinator', manager: 'care manager', carer: 'carer' } as const

/**
 * Renders the page if the role has its permission; otherwise the access-denied state.
 * The API is the real gate: this only avoids showing a page that can't load. On denial we
 * still call the page's API read so the server refuses it and audits the attempt.
 */
export function Guarded({ pageKey, children }: { pageKey: PageKey; children: ReactNode }) {
  const { me, can } = useAuth()
  const def = page(pageKey)
  const allowed = can(def.permission)
  const [recorded, setRecorded] = useState(false)

  useEffect(() => {
    if (allowed) return
    let live = true
    def
      .probe()
      .then(({ response }) => live && setRecorded(response.status === 403))
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [allowed, def])

  if (allowed) return children
  const name = me ? `${me.display_name || me.username} (${ROLE_WORD[me.role]})` : ''
  const back =
    me?.role === 'carer'
      ? { label: 'Back to my visits', to: CARER_APP_URL, external: true }
      : { label: 'Back to overview', to: '/' }
  return (
    <>
      <PageHeader title={def.title} />
      <div className="flex min-h-[420px]">
        <AccessDenied subject={def.deniedSubject} signedInAs={name} back={back} recorded={recorded} />
      </div>
    </>
  )
}
