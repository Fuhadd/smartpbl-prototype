/**
 * Provider protocols shown beside a flagged note. The design ships a placeholder for
 * falls only; PBL Care supplies the real wording (KTP knowledge transfer). Categories
 * without an entry show no protocol card.
 */
import type { Category } from './categories'

export const PROTOCOLS: Partial<Record<Category, string>> = {
  falls:
    "[PLACEHOLDER: PBL's falls protocol — e.g. after an unwitnessed fall, notify the GP and next of kin, and review the falls risk assessment within 24 hours.]",
}
