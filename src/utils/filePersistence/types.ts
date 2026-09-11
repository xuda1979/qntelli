// Stub: file-persistence types & constants (omitted from snapshot).
export const OUTPUTS_SUBDIR = 'outputs'
export const FILE_COUNT_LIMIT = 200
export const DEFAULT_UPLOAD_CONCURRENCY = 4

export type TurnStartTime = number
export interface PersistedFile {
  path: string
  content: string
  encoding?: string
}
export interface FailedPersistence {
  path: string
  error: string
}
export interface FilesPersistedEventData {
  files: PersistedFile[]
  failed: FailedPersistence[]
  sessionId: string
}
