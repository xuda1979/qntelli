// Stub: connector-text feature is not enabled in this build.
// Provided because the leaked snapshot omits this module, but imports
// reference it. Guard always returns false when the feature is off.
export interface ConnectorTextBlock {
  type: 'connector_text'
  text: string
  connector_type: string
}

export function isConnectorTextBlock(
  block: unknown,
): block is ConnectorTextBlock {
  if (typeof block !== 'object' || block === null) return false
  const b = block as Record<string, unknown>
  return b?.type === 'connector_text'
}
