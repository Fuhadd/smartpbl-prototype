/**
 * The dashboard's pages: rail item, title, required permission and access-denied copy.
 * Routes, the rail and the guards all read this one table, mirroring the API's
 * route -> permission table (app/auth/permissions.py).
 */
import { ClipboardList, LayoutGrid, MapPin, MessageSquareCheck, Users, type LucideIcon } from 'lucide-react'

import { api } from '@/api/client'
import type { Permission } from '@/auth/auth'

const NIL = '00000000-0000-0000-0000-000000000000'

export type PageKey = 'overview' | 'review' | 'schedule' | 'workforce' | 'audit'

export type PageDef = {
  key: PageKey
  to: string
  title: string
  navLabel: string
  icon: LucideIcon
  permission: Permission
  /** First sentence of the access-denied message. */
  deniedSubject: string
  /**
   * The page's own API read. When the role lacks the permission we still make it, so the
   * server (not the browser) refuses it with 403 and its audit middleware records the
   * attempt. The design's "This attempt was recorded" line is shown only after that 403.
   */
  probe: () => Promise<{ response: Response }>
}

export const PAGES: readonly PageDef[] = [
  {
    key: 'overview',
    to: '/',
    title: 'Overview',
    navLabel: 'Overview',
    icon: LayoutGrid,
    permission: 'review.queue.read',
    deniedSubject: 'The overview is visible to coordinators and care managers.',
    probe: () => api.GET('/review/queue', { params: { query: { limit: 1 } } }),
  },
  {
    key: 'review',
    to: '/review',
    title: 'Review',
    navLabel: 'Review queue',
    icon: MessageSquareCheck,
    permission: 'review.queue.read',
    deniedSubject: 'Care-note review is visible to coordinators and care managers.',
    probe: () => api.GET('/review/queue', { params: { query: { limit: 1 } } }),
  },
  {
    key: 'schedule',
    to: '/schedule',
    title: 'Schedule',
    navLabel: 'Schedule',
    icon: MapPin,
    permission: 'schedule.read',
    deniedSubject: 'The schedule is visible to coordinators and care managers.',
    probe: () => api.GET('/schedule/{run_id}', { params: { path: { run_id: NIL } } }),
  },
  {
    key: 'workforce',
    to: '/workforce',
    title: 'Workforce',
    navLabel: 'Workforce',
    icon: Users,
    permission: 'workforce.read',
    deniedSubject: 'Workforce risk is visible to coordinators and care managers.',
    probe: () => api.GET('/workforce/risk', { params: { query: { limit: 1 } } }),
  },
  {
    key: 'audit',
    to: '/audit',
    title: 'Audit log',
    navLabel: 'Audit log',
    icon: ClipboardList,
    permission: 'audit.read',
    deniedSubject: 'The audit log is visible to coordinators and care managers.',
    probe: () => api.GET('/audit/{note_id}', { params: { path: { note_id: NIL } } }),
  },
]

export function page(key: PageKey): PageDef {
  const found = PAGES.find((p) => p.key === key)
  if (!found) throw new Error(`unknown page ${key}`)
  return found
}
