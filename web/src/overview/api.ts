/** Server state for the overview (TanStack Query). One request feeds every panel. */
import { useQuery } from '@tanstack/react-query'

import { api, toApiError } from '@/api/client'
import type { components } from '@/api/schema'

export type Overview = components['schemas']['OverviewOut']
export type AttentionNote = components['schemas']['AttentionNote']
export type ScheduleSummary = components['schemas']['ScheduleSummary']

export const overviewKey = ['overview'] as const

export function useOverview() {
  return useQuery({
    queryKey: overviewKey,
    queryFn: async () => {
      const r = await api.GET('/overview')
      if (!r.data) throw await toApiError(r.response, r.error)
      return r.data
    },
  })
}
