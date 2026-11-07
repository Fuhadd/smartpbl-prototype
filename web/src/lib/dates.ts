/** Date copy used by the overview header. */

export function greeting(now: Date): string {
  const h = now.getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

/** "Saturday, 7 November": the design's format (en-GB alone omits the comma). */
export function longDate(now: Date): string {
  const weekday = now.toLocaleDateString('en-GB', { weekday: 'long' })
  const dayMonth = now.toLocaleDateString('en-GB', { day: 'numeric', month: 'long' })
  return `${weekday}, ${dayMonth}`
}
