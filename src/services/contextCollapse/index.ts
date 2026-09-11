// Stub: context-collapse store (omitted from snapshot).
// Implements the minimal getStats/subscribe surface TokenWarning uses.
export interface ContextCollapseStats {
  collapsedChars: number
  collapseCount: number
}

const listeners = new Set<() => void>()
let stats: ContextCollapseStats = { collapsedChars: 0, collapseCount: 0 }

export function getStats(): ContextCollapseStats {
  return { ...stats }
}
export function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
