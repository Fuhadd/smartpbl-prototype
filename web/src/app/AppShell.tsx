/**
 * Shared web layout (DESIGN.md section 3): a 76 px white rail with icon nav, and a header
 * with breadcrumb, the always-visible "Demo data · synthetic" badge, search, notifications
 * and the signed-in user. Content sits in a max-width 1240 px container.
 */
import { Bell, Search } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router'

import { initials, ROLE_LABEL, useAuth } from '@/auth/auth'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import { PAGES } from './pages'

export function AppShell() {
  const { can } = useAuth()
  return (
    <div className="flex min-h-screen flex-wrap bg-bg text-text">
      <nav
        aria-label="Main"
        className="flex flex-[0_0_76px] flex-col items-center gap-2 border-r border-border bg-surface py-5"
      >
        <div className="mb-4 flex size-10 items-center justify-center rounded-lg bg-primary text-[17px] font-bold text-primary-foreground">
          S
        </div>
        {PAGES.filter((p) => can(p.permission)).map((p) => (
          <NavLink
            key={p.key}
            to={p.to}
            end={p.to === '/'}
            aria-label={p.navLabel}
            title={p.navLabel}
            className={({ isActive }) =>
              cn(
                'flex size-12 items-center justify-center rounded-[14px] focus-visible:outline-2 focus-visible:outline-primary',
                isActive ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-surface-muted',
              )
            }
          >
            <p.icon size={22} strokeWidth={1.75} aria-hidden="true" />
          </NavLink>
        ))}
      </nav>
      <main className="min-w-0 flex-[999_1_560px] px-10 pt-7 pb-12 max-sm:px-4">
        <div className="mx-auto flex max-w-[1240px] flex-col gap-7">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

export function DemoBadge() {
  return (
    <Badge variant="demo" className="text-xs">
      Demo data · synthetic
    </Badge>
  )
}

/** The header row at the top of every page. */
export function PageHeader({ title, trail }: { title: string; trail?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-muted-foreground">SMARTPBL</span>
        <span className="text-sm text-faint" aria-hidden="true">
          /
        </span>
        <span className="text-sm font-semibold">{title}</span>
        {trail}
        <DemoBadge />
      </div>
      <div className="flex items-center gap-2.5">
        <label className="flex h-11 w-[260px] items-center gap-2 rounded-full border border-border bg-surface px-4 text-muted-foreground max-sm:w-full">
          <Search size={18} strokeWidth={1.75} aria-hidden="true" />
          <span className="sr-only">Search</span>
          <input
            type="search"
            placeholder="Search clients, carers, notes"
            className="w-full border-0 bg-transparent text-sm text-text outline-none"
          />
        </label>
        <button
          type="button"
          aria-label="Notifications"
          className="flex size-11 cursor-pointer items-center justify-center rounded-full border border-border bg-surface text-text"
        >
          <Bell size={18} strokeWidth={1.75} aria-hidden="true" />
        </button>
        <UserChip />
      </div>
    </header>
  )
}

/** The signed-in user. Not in the design: clicking it offers "Sign out" (design gap). */
function UserChip() {
  const { me, signOut } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => ref.current?.contains(e.target as Node) || setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  if (!me) return null
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex h-11 cursor-pointer items-center gap-2.5 rounded-full border border-border bg-surface py-1 pr-3.5 pl-1"
      >
        <span className="flex size-[34px] items-center justify-center rounded-full bg-avatar text-[13px] font-semibold text-ai-text">
          {initials(me)}
        </span>
        <span className="text-sm font-medium">{ROLE_LABEL[me.role]}</span>
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-2 flex min-w-[200px] flex-col gap-1 rounded-2xl border border-border bg-surface p-2">
          <span className="px-3 pt-1 text-[13px] text-muted-foreground">{me.display_name || me.username}</span>
          <button
            type="button"
            onClick={async () => {
              await signOut()
              navigate('/login', { replace: true })
            }}
            className="h-10 cursor-pointer rounded-xl px-3 text-left text-sm font-semibold hover:bg-surface-muted"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}
