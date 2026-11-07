/** Server state for the review screen (TanStack Query). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, toApiError } from '@/api/client'
import type { components } from '@/api/schema'

export type QueueItem = components['schemas']['QueueItem']
export type Note = components['schemas']['NoteOut']
export type Flag = components['schemas']['FlagOut']
export type FlagDecision = components['schemas']['FlagDecision']

export const queueKey = ['review', 'queue'] as const
export const noteKey = (id: string) => ['notes', id] as const

export function useQueue() {
  return useQuery({
    queryKey: queueKey,
    queryFn: async () => {
      const r = await api.GET('/review/queue', { params: { query: { limit: 200 } } })
      if (!r.data) throw await toApiError(r.response, r.error)
      return r.data
    },
  })
}

export function useNote(id: string | undefined) {
  return useQuery({
    queryKey: noteKey(id ?? ''),
    enabled: Boolean(id),
    queryFn: async () => {
      const r = await api.GET('/notes/{note_id}', { params: { path: { note_id: id! } } })
      if (!r.data) throw await toApiError(r.response, r.error)
      return r.data
    },
  })
}

export function useDecideNote(noteId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (body: { decisions: FlagDecision[]; escalate: boolean }) => {
      const r = await api.POST('/review/notes/{note_id}', { params: { path: { note_id: noteId } }, body })
      if (!r.data) throw await toApiError(r.response, r.error)
      return r.data
    },
    onSuccess: (out) => {
      client.setQueryData(noteKey(noteId), out.note)
      return client.invalidateQueries({ queryKey: queueKey })
    },
  })
}
