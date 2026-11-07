import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

import { tokenStore } from '@/auth/tokens'

afterEach(() => {
  cleanup()
  tokenStore.set(null)
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
