/**
 * The session's tokens, held in memory only (ADR-027): never localStorage, sessionStorage
 * or cookies, so an injected script can't harvest them from storage and no other site can
 * make the browser send them. The cost: a page reload signs the user out.
 */
export type Tokens = { access: string; refresh: string }

type Listener = (tokens: Tokens | null) => void

let current: Tokens | null = null
const listeners = new Set<Listener>()

export const tokenStore = {
  get: (): Tokens | null => current,
  set(tokens: Tokens | null): void {
    current = tokens
    for (const listener of listeners) listener(current)
  },
  subscribe(listener: Listener): () => void {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
}
