/** Server state for the schedule screen (TanStack Query). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, ApiError, toApiError } from '@/api/client'
import type { components } from '@/api/schema'
import { overviewKey } from '@/overview/api'

export type Run = components['schemas']['ScheduleOut']
export type CarerRoute = components['schemas']['CarerRoute']
export type Assignment = components['schemas']['AssignmentOut']
export type RunMap = components['schemas']['RunMap']
export type Tradeoff = components['schemas']['TradeoffOut']
export type Preset = components['schemas']['Preset']

export const latestKey = ['schedule', 'latest'] as const
/** Per solve phase; a solve with continuity runs two phases, so up to ~20 s in total. */
export const SOLVE_TIME_LIMIT_S = 10

export function useLatestSchedule() {
  return useQuery({
    queryKey: latestKey,
    queryFn: async (): Promise<Run | null> => {
      const r = await api.GET('/schedule/latest')
      if (r.response.status === 404) return null // nothing saved yet: an empty state, not an error
      if (!r.data) throw await toApiError(r.response, r.error)
      return r.data
    },
  })
}

/** Locations for the map. `null` when the run isn't the sample day (runs don't store them). */
export function useRunMap(runId: string | undefined) {
  return useQuery({
    queryKey: ['schedule', runId, 'map'],
    enabled: Boolean(runId),
    staleTime: Infinity, // a run's places never change
    queryFn: async (): Promise<RunMap | null> => {
      const r = await api.GET('/schedule/{run_id}/map', { params: { path: { run_id: runId! } } })
      if (r.response.status === 404) return null
      if (!r.data) throw await toApiError(r.response, r.error)
      return r.data
    },
  })
}

export function useTradeoff() {
  return useQuery({
    queryKey: ['schedule', 'tradeoff'],
    staleTime: Infinity,
    queryFn: async () => {
      const r = await api.GET('/schedule/tradeoff')
      if (!r.data) throw await toApiError(r.response, r.error)
      return r.data
    },
  })
}

export function useSolve() {
  const client = useQueryClient()
  return useMutation<Run, ApiError, number>({
    mutationFn: async (continuityWeightMin) => {
      const r = await api.POST('/schedule/solve', {
        body: { continuity_weight_min: continuityWeightMin, time_limit_s: SOLVE_TIME_LIMIT_S },
      })
      if (!r.data) throw await toApiError(r.response, r.error)
      return r.data
    },
    onSuccess: (run) => {
      client.setQueryData(latestKey, run)
      return client.invalidateQueries({ queryKey: overviewKey })
    },
  })
}
