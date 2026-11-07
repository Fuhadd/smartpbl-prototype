/** Server state for the workforce screen (TanStack Query). Every read is audited server-side. */
import { useQuery } from '@tanstack/react-query'

import { api, toApiError } from '@/api/client'
import type { components } from '@/api/schema'

export type RiskList = components['schemas']['RiskList']
export type RiskItem = components['schemas']['RiskItem']
export type Explanation = components['schemas']['ExplanationOut']
export type Factor = components['schemas']['FactorOut']
export type Band = components['schemas']['RiskBand']

/** The whole current workforce (200 carers): the list panel scrolls rather than pages. */
export const LIST_LIMIT = 200

export function useRiskList() {
  return useQuery({
    queryKey: ['workforce', 'risk'],
    staleTime: 5 * 60_000, // scores only change when the model is retrained
    queryFn: async () => {
      const r = await api.GET('/workforce/risk', { params: { query: { limit: LIST_LIMIT } } })
      if (!r.data) throw await toApiError(r.response, r.error)
      return r.data
    },
  })
}

/** One carer's explanation; `null` when the ref isn't in the current workforce (404). */
export function useExplanation(carerRef: string | undefined) {
  return useQuery({
    queryKey: ['workforce', carerRef, 'explanation'],
    enabled: Boolean(carerRef),
    staleTime: 5 * 60_000,
    queryFn: async (): Promise<Explanation | null> => {
      const r = await api.GET('/workforce/{carer_ref}/explanation', { params: { path: { carer_ref: carerRef! } } })
      if (r.response.status === 404 || r.response.status === 422) return null
      if (!r.data) throw await toApiError(r.response, r.error)
      return r.data
    },
  })
}
