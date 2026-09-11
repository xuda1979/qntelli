// Stub for the native modifiers-napi module (internal package, not on the
// public registry). Mirrors the future-code build stub: no-op prewarm, and
// isModifierPressed always false. The real module is darwin-only and
// try/catch-guarded at its call sites, so behavior is unchanged on Linux.

export function prewarm(): void {}

export function isModifierPressed(_m: string): boolean {
  return false
}

const _default: any = { prewarm, isModifierPressed }
export default _default
