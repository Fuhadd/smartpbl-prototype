/**
 * Risk categories as the designs present them. Falls, nutrition and mood colours are
 * from DESIGN.md / Review.dc.html; the other four are not in the designs and were
 * chosen to sit in the same pastel family (design gap).
 */
import type { components } from '@/api/schema'

export type Category = components['schemas']['RiskCategory']
export type Severity = components['schemas']['Severity']

type CategoryStyle = { label: string; short: string; swatch: string; highlight: string }

export const CATEGORY: Record<Category, CategoryStyle> = {
  falls: { label: 'Falls', short: 'Falls', swatch: '#F38744', highlight: '#FEEBD8' },
  nutrition_hydration: { label: 'Nutrition / hydration', short: 'Nutrition', swatch: '#5AA2F7', highlight: '#DCEBFE' },
  mood_behaviour: { label: 'Mood / behaviour change', short: 'Mood', swatch: '#8B80F0', highlight: '#EAE7FD' },
  medication: { label: 'Medication', short: 'Medication', swatch: '#EE46BC', highlight: '#FCE7F6' },
  skin_integrity: { label: 'Skin integrity', short: 'Skin integrity', swatch: '#E8A317', highlight: '#FEF0C7' },
  safeguarding: { label: 'Safeguarding concern', short: 'Safeguarding', swatch: '#F04438', highlight: '#FEE4E2' },
  missed_late_visit: { label: 'Missed / late visit', short: 'Missed visit', swatch: '#667085', highlight: '#EAECF0' },
}

export const SEVERITY_LABEL: Record<Severity, string> = { high: 'High', medium: 'Medium', low: 'Low' }

export const CATEGORIES = Object.keys(CATEGORY) as Category[]
export const SEVERITIES: Severity[] = ['high', 'medium', 'low']
