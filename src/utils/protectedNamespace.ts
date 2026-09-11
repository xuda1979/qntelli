// Stub: internal Anthropic protected-namespace check. External builds
// never run with USER_TYPE==='ant', so we always report unprotected.
export function checkProtectedNamespace(): boolean {
  return false
}
