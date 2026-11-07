/** Build-time configuration (Vite `VITE_*` variables) and demo-mode copy. */

/** The Flutter carer app (Step 5.6). The sign-in screen's "Carer app" link opens it. */
export const CARER_APP_URL: string = import.meta.env.VITE_CARER_APP_URL ?? 'http://localhost:8081'

/** Shown under the greeting: "Saturday, 7 November · Birmingham South team". */
export const TEAM_NAME: string = import.meta.env.VITE_TEAM_NAME ?? 'Birmingham South team'

export type DemoRole = 'coordinator' | 'manager' | 'carer'

/** Public demo accounts, exactly as on docs/design/screens/Login.dc.html (seeded by
 * scripts/seed_demo.py; refused outside local/demo environments). */
export const DEMO_ACCOUNTS: Record<DemoRole, { label: string; email: string; password: string }> = {
  coordinator: { label: 'Coordinator', email: 'hannah@demo.smartpbl', password: 'demo-coordinator' },
  manager: { label: 'Care manager', email: 'sam@demo.smartpbl', password: 'demo-manager' },
  carer: { label: 'Carer', email: 'joy@demo.smartpbl', password: 'demo-carer' },
}
