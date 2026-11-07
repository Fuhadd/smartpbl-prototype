import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'

import { AuditPage } from '@/pages/AuditPage'
import { LazySchedulePage } from '@/pages/LazySchedulePage'
import { LoginPage } from '@/pages/LoginPage'
import { OverviewPage } from '@/pages/OverviewPage'
import { PendingPage as Pending } from '@/pages/PendingPage'
import { ReviewPage } from '@/pages/ReviewPage'

import { AppShell } from './AppShell'
import { Guarded, RequireAuth } from './guards'

// Routes from DESIGN.md section 2.
export const routes: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  {
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Guarded pageKey="overview"><OverviewPage /></Guarded> },
      { path: 'review/:noteId?', element: <Guarded pageKey="review"><ReviewPage /></Guarded> },
      { path: 'schedule', element: <Guarded pageKey="schedule"><LazySchedulePage /></Guarded> },
      { path: 'workforce/:carerId?', element: <Guarded pageKey="workforce"><Pending pageKey="workforce" step="5.4" /></Guarded> },
      { path: 'audit', element: <Guarded pageKey="audit"><AuditPage /></Guarded> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]

export const createRouter = () => createBrowserRouter(routes)
