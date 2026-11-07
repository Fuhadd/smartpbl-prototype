/** Sign in: docs/design/screens/Login.dc.html. */
import { MapPin, Sparkle, UserRound } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router'

import { ApiError } from '@/api/client'
import { useAuth } from '@/auth/auth'
import { CARER_APP_URL, DEMO_ACCOUNTS } from '@/config'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { cn } from '@/lib/utils'

type WebRole = 'coordinator' | 'manager'

const FEATURES: { icon: ReactNode; text: string }[] = [
  { icon: <Sparkle size={16} strokeWidth={1.75} />, text: 'Care notes read for risks, with evidence' },
  { icon: <MapPin size={16} strokeWidth={1.75} />, text: 'Rotas balancing travel and continuity' },
  { icon: <UserRound size={16} strokeWidth={1.75} />, text: 'Early, explainable signals to support carers' },
]

const SEGMENT = 'h-10 w-full'
const INPUT = 'h-[50px] rounded-lg bg-surface px-3.5 text-[15px] shadow-none md:text-[15px]'
const LABEL = 'text-[13px] font-semibold'

/** Messages for the failure states the design doesn't draw (see learning note 24). */
function signInError(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) return 'Email or password is incorrect.'
  if (error instanceof ApiError && error.status === 429)
    return `Too many sign-in attempts. Try again in ${error.retryAfterS ?? 60} seconds.`
  if (error instanceof ApiError)
    return `Sign-in failed. Please try again.${error.reference ? ` Reference: ${error.reference}` : ''}`
  return "Couldn't reach the server. Check your connection and try again."
}

export function LoginPage() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const from = (useLocation().state as { from?: string } | null)?.from ?? '/'
  const [role, setRole] = useState<WebRole>('coordinator')
  const [email, setEmail] = useState(DEMO_ACCOUNTS.coordinator.email)
  const [password, setPassword] = useState(DEMO_ACCOUNTS.coordinator.password)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const choose = (next: WebRole) => {
    setRole(next)
    setEmail(DEMO_ACCOUNTS[next].email)
    setPassword(DEMO_ACCOUNTS[next].password)
    setError(null)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await signIn(email.trim(), password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(signInError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="box-border flex min-h-screen flex-wrap gap-5 bg-bg p-5 text-text">
      <section
        aria-label="About SMARTPBL"
        className="box-border flex min-w-0 flex-[1_1_420px] flex-col justify-between gap-10 rounded-[28px] bg-primary p-12 text-white max-sm:p-8"
      >
        <div className="flex items-center gap-3">
          <div className="flex size-11 items-center justify-center rounded-lg bg-white text-lg font-bold text-primary">
            S
          </div>
          <span className="text-lg font-semibold">SMARTPBL</span>
        </div>
        <div className="flex max-w-[480px] flex-col gap-5">
          <h1 className="m-0 text-[40px] leading-[1.1] font-bold tracking-[-0.02em]">
            Safer visits, fairer rotas, a steadier team.
          </h1>
          <ul className="m-0 flex list-none flex-col gap-3.5 p-0 text-[15px] text-[#E4E4E7]">
            {FEATURES.map((f) => (
              <li key={f.text} className="flex items-center gap-3">
                <span
                  aria-hidden="true"
                  className="flex size-8 flex-[0_0_32px] items-center justify-center rounded-[10px] bg-[#2A2A2E]"
                >
                  {f.icon}
                </span>
                {f.text}
              </li>
            ))}
          </ul>
        </div>
        <p className="m-0 text-[13px] text-faint">A portfolio prototype. All people and data are synthetic.</p>
      </section>

      <main className="box-border flex min-w-0 flex-[1_1_420px] items-center justify-center px-4 py-8">
        <div className="flex w-full max-w-[420px] flex-col gap-6">
          <div className="flex flex-col gap-1.5">
            <h2 className="m-0 text-[28px] font-bold tracking-[-0.02em]">Sign in</h2>
            <p className="m-0 text-[15px] text-muted-foreground">Choose a demo role to explore what each user sees.</p>
          </div>

          <div className="grid grid-cols-3 gap-1 rounded-xl border border-border bg-surface p-1">
            <ToggleGroup
              type="single"
              variant="segment"
              spacing={1}
              aria-label="Demo role"
              value={role}
              // Radix allows deselecting; a role must always be chosen.
              onValueChange={(v) => v && choose(v as WebRole)}
              className="col-span-2 grid w-full grid-cols-2"
            >
              {(['coordinator', 'manager'] as const).map((r) => (
                <ToggleGroupItem key={r} value={r} className={SEGMENT}>
                  {DEMO_ACCOUNTS[r].label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            {/* A link, not a role: carers use the separate Flutter app (Step 5.6). */}
            <a
              href={CARER_APP_URL}
              className={cn(SEGMENT, 'flex items-center justify-center rounded-[10px] text-[13px] font-medium text-soft')}
            >
              Carer app
            </a>
          </div>

          <form onSubmit={submit} className="flex flex-col gap-3.5" noValidate>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email" className={LABEL}>
                Email
              </Label>
              {/* type="text" + inputMode="email": looks and types like the design's email
                  field, but also accepts non-email usernames created with the CLI. */}
              <Input
                id="email"
                type="text"
                inputMode="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={INPUT}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pass" className={LABEL}>
                Password
              </Label>
              <Input
                id="pass"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={INPUT}
              />
            </div>
            {error && (
              <p role="alert" className="m-0 text-[13px] font-medium text-high">
                {error}
              </p>
            )}
            <Button type="submit" size="xl" disabled={busy} className="mt-1 cursor-pointer">
              Sign in
            </Button>
          </form>

          <Card
            aria-labelledby="creds"
            role="region"
            className="gap-2.5 rounded-2xl border-0 bg-surface px-[18px] py-4 shadow-none"
          >
            <h3 id="creds" className="m-0 text-[13px] font-semibold">
              Demo accounts
            </h3>
            <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[13px]">
              {Object.values(DEMO_ACCOUNTS).map((a) => (
                <span key={a.email} className="contents">
                  <span className="text-muted-foreground">{a.label}</span>
                  <span className="font-mono">
                    {a.email} · {a.password}
                  </span>
                </span>
              ))}
            </div>
          </Card>
        </div>
      </main>
    </div>
  )
}
