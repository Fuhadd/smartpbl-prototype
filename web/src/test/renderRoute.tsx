/** Render the real route table at `path`, signed in as `me`, against a fake API. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'

import { routes } from '@/app/router'
import { AuthContext, type Me } from '@/auth/auth'

import { ME } from './fakeApi'

export function renderRoute(path: string, me: Me = ME.coordinator as unknown as Me) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const auth = { me, signIn: async () => me, signOut: async () => {}, can: (p: string) => me.permissions.includes(p as never) }
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AuthContext value={auth}>
        <RouterProvider router={router} />
      </AuthContext>
    </QueryClientProvider>,
  )
  return router
}
