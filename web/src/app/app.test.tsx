/** Sign-in, role-aware navigation and access-denied: the whole app in a memory router. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '@/auth/AuthProvider'
import { fakeApi, json, ME, TOKENS } from '@/test/fakeApi'
import { overviewFixture } from '@/test/fixtures'

import { routes } from './router'

function renderApp(path = '/') {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return router
}

function backend(me: (typeof ME)[keyof typeof ME]) {
  return fakeApi({
    'POST /auth/token': async (req) => {
      const form = new URLSearchParams(await req.text())
      return form.get('password') === 'demo-coordinator' || form.get('password') === 'demo-carer'
        ? json(TOKENS)
        : json({ detail: 'not authenticated' }, 401)
    },
    'GET /auth/me': () => json(me),
    'GET /overview': () => json(overviewFixture()),
    'GET /workforce/risk': () => json({ detail: 'insufficient permissions' }, 403),
    'POST /auth/logout': () => new Response(null, { status: 204 }),
  })
}

describe('sign in', () => {
  it('shows the design copy with the coordinator demo account pre-filled', () => {
    backend(ME.coordinator)
    renderApp('/login')
    expect(screen.getByRole('heading', { name: 'Safer visits, fairer rotas, a steadier team.' })).toBeInTheDocument()
    expect(screen.getByText('Choose a demo role to explore what each user sees.')).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveValue('hannah@demo.smartpbl')
    expect(screen.getByLabelText('Password')).toHaveValue('demo-coordinator')
    expect(screen.getByRole('radio', { name: 'Coordinator' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText('joy@demo.smartpbl · demo-carer')).toBeInTheDocument()
    expect(screen.getByText('A portfolio prototype. All people and data are synthetic.')).toBeInTheDocument()
  })

  it('switches the pre-filled account with the role control', async () => {
    backend(ME.coordinator)
    renderApp('/login')
    await userEvent.click(screen.getByRole('radio', { name: 'Care manager' }))
    expect(screen.getByLabelText('Email')).toHaveValue('sam@demo.smartpbl')
    expect(screen.getByRole('radio', { name: 'Care manager' })).toHaveAttribute('aria-checked', 'true')
    // Clicking the selected role again must not leave no role selected.
    await userEvent.click(screen.getByRole('radio', { name: 'Care manager' }))
    expect(screen.getByRole('radio', { name: 'Care manager' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('link', { name: 'Carer app' })).toHaveAttribute('href', 'http://localhost:8081')
  })

  it('signs in and lands on the overview greeting', async () => {
    const { calls } = backend(ME.coordinator)
    const router = renderApp('/login')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText(/, Hannah$/)).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/')
    expect(screen.getByText('Demo data · synthetic')).toBeInTheDocument()
    const form = new URLSearchParams(calls.find((c) => c.path === '/auth/token')!.body)
    expect(form.get('username')).toBe('hannah@demo.smartpbl')
    expect(calls.find((c) => c.path === '/auth/me')?.auth).toBe('Bearer A1')
  })

  it('explains a wrong password without saying which field was wrong', async () => {
    backend(ME.coordinator)
    renderApp('/login')
    await userEvent.clear(screen.getByLabelText('Password'))
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-password')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Email or password is incorrect.')
  })

  it('shows an unexpected failure with its request reference, not "can\'t reach the server"', async () => {
    fakeApi({ 'POST /auth/token': () => json({ detail: 'boom' }, 500) })
    renderApp('/login')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Sign-in failed. Please try again. Reference: req_8f2c41')
  })

  it('shows the wait time when sign-in is rate limited', async () => {
    fakeApi({ 'POST /auth/token': () => json({ detail: 'too many requests' }, 429, { 'retry-after': '37' }) })
    renderApp('/login')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Try again in 37 seconds.')
  })

  it('sends signed-out visitors to sign-in, then back to where they were going', async () => {
    backend(ME.coordinator)
    const router = renderApp('/schedule')
    expect(router.state.location.pathname).toBe('/login')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/schedule'))
  })
})

async function signInAs(me: (typeof ME)[keyof typeof ME], path: string) {
  const api = backend(me)
  const router = renderApp(path)
  if (me.role === 'carer') {
    await userEvent.clear(screen.getByLabelText('Password'))
    await userEvent.type(screen.getByLabelText('Password'), 'demo-carer')
  }
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  return { api, router }
}

describe('role-aware shell', () => {
  it('shows a coordinator every rail item, with the current page marked', async () => {
    await signInAs(ME.coordinator, '/workforce')
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    const labels = within(nav)
      .getAllByRole('link')
      .map((a) => a.getAttribute('aria-label'))
    expect(labels).toEqual(['Overview', 'Review queue', 'Schedule', 'Workforce', 'Audit log'])
    expect(within(nav).getByRole('link', { name: 'Workforce' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('HK')).toBeInTheDocument()
  })

  it("denies a carer the workforce page in the design's words, after the server refused", async () => {
    const { api } = await signInAs(ME.carer, '/workforce')
    expect(await screen.findByRole('heading', { name: "You don't have access to this page" })).toBeInTheDocument()
    expect(
      screen.getByText(/Workforce risk is visible to coordinators and care managers\. You're signed in as/),
    ).toBeInTheDocument()
    expect(screen.getByText('Joy A. (carer)')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to my visits' })).toHaveAttribute('href', 'http://localhost:8081')
    // The attempt reached the API (whose middleware audits the 403) before we claim it was recorded.
    expect(await screen.findByText('This attempt was recorded in the audit log.')).toBeInTheDocument()
    expect(api.calls.some((c) => c.method === 'GET' && c.path === '/workforce/risk')).toBe(true)
    expect(within(screen.getByRole('navigation', { name: 'Main' })).queryAllByRole('link')).toHaveLength(0)
  })

  it('signs out from the user chip', async () => {
    const { api, router } = await signInAs(ME.coordinator, '/')
    await userEvent.click(await screen.findByRole('button', { name: /Coordinator/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(api.calls.find((c) => c.path === '/auth/logout')?.body).toContain('"refresh_token":"R1"')
  })
})
