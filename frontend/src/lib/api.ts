import { supabase } from './supabase'

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

export type Role = 'submitter' | 'reviewer'
export type Status = 'pending' | 'approved' | 'rejected'

export interface Identity {
  id: string
  email: string
  display_name: string
  role: Role
}

export interface ProfileSummary {
  id: string
  display_name: string
  email: string
  role: Role
}

export interface Submission {
  id: string
  title: string
  context: string
  status: Status
  original_filename: string
  file_size_bytes: number
  content_type: string
  created_at: string
  submitted_by: ProfileSummary
  reviewed_by: ProfileSummary | null
  reviewed_at: string | null
  decision_note: string
}

export interface SubmissionList {
  results: Submission[]
  counts: Record<string, number>
}

/** A failure the UI can branch on, carrying the backend's stable error code. */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
    readonly fieldErrors: Record<string, string[]> = {},
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) {
    throw new ApiError('no_session', 'Your session has ended. Please sign in again.', 401)
  }
  return { Authorization: `Bearer ${token}` }
}

async function toError(response: Response): Promise<ApiError> {
  let code = 'request_failed'
  let message = 'Something went wrong. Please try again.'
  let fieldErrors: Record<string, string[]> = {}
  try {
    const body = await response.json()
    if (body?.error) {
      code = body.error.code ?? code
      message = body.error.message ?? message
      fieldErrors = body.error.field_errors ?? {}
    }
  } catch {
    // A non-JSON body means the server or a proxy failed before our handler.
    if (response.status >= 500) {
      message = 'The service is unavailable right now. Please try again.'
    }
  }
  return new ApiError(code, message, response.status, fieldErrors)
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = { ...(await authHeader()), ...(init.headers ?? {}) }

  let response: Response
  try {
    response = await fetch(`${baseUrl}${path}`, { ...init, headers })
  } catch {
    // Distinguish "cannot reach the API" from "the API said no". On free
    // hosting the server may be waking up, which is not a failure to hide.
    throw new ApiError(
      'network_unreachable',
      'Could not reach the server. It may be starting up — please try again.',
      0,
    )
  }

  if (!response.ok) throw await toError(response)
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

export const api = {
  me: () => request<Identity>('/api/me/'),

  listSubmissions: (status?: string) =>
    request<SubmissionList>(
      `/api/submissions/${status && status !== 'all' ? `?status=${encodeURIComponent(status)}` : ''}`,
    ),

  getSubmission: (id: string) => request<Submission>(`/api/submissions/${id}/`),

  // Minted on demand and never stored: it is a bearer link with a short expiry.
  getFileUrl: (id: string) =>
    request<{ url: string; expires_at: string }>(`/api/submissions/${id}/file-url/`),

  createSubmission: (input: { title: string; context: string; file: File }) => {
    const form = new FormData()
    form.append('title', input.title)
    form.append('context', input.context)
    form.append('file', input.file)
    // No Content-Type header: the browser must set the multipart boundary.
    return request<Submission>('/api/submissions/', { method: 'POST', body: form })
  },

  decide: (id: string, decision: 'approve' | 'reject', note: string) =>
    request<Submission>(`/api/submissions/${id}/decision/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, note }),
    }),
}
