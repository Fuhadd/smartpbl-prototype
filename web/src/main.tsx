import './index.css'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'

import { createRouter } from '@/app/router'
import { AuthProvider } from '@/auth/AuthProvider'

const queryClient = new QueryClient({
  // Data is personal; don't keep stale copies around longer than needed.
  defaultOptions: { queries: { retry: 1, gcTime: 5 * 60_000, refetchOnWindowFocus: false } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={createRouter()} />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
)
