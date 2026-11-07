/** Review-queue logic: filters and item titles. */
import type { QueueItem } from './api'
import { CATEGORY } from './categories'

export type QueueFilter = 'all' | 'high' | 'medium'
export const FILTERS: { key: QueueFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'high', label: 'High' },
  { key: 'medium', label: 'Medium' },
]

export function applyFilter(items: QueueItem[], filter: QueueFilter): QueueItem[] {
  return filter === 'all' ? items : items.filter((i) => i.priority === filter)
}

export function queueTitle(item: QueueItem): string {
  const top = item.pending_flags[0]
  // A carer's urgent concern can arrive with no flags at all: say what it is, not "failed".
  const what = top ? CATEGORY[top.category].short : item.urgent ? 'Urgent concern' : 'Extraction failed'
  return `${item.client_ref} · ${what}`
}
