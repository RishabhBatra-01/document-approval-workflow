import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { api, ApiError, type Submission, type SubmissionList } from '../lib/api'
import { AppShell } from '../components/AppShell'
import { Icon } from '../components/Icon'
import {
  ActivityTrail,
  EmptyState,
  ErrorNotice,
  StatusBadge,
  TableSkeleton,
  formatDate,
  formatSize,
  shouldIgnoreRowClick,
} from '../components/common'

/** How long the confirmation message stays before it clears itself. */
const CONFIRMATION_MS = 6000

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'pending', label: 'Pending' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
] as const

export function MySubmissions() {
  const [data, setData] = useState<SubmissionList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // Set by the upload page on a successful submit, so the list can confirm it
  // landed rather than silently growing a row.
  const location = useLocation()
  const navigate = useNavigate()
  const created = (location.state ?? {}) as { createdId?: string; createdTitle?: string }
  // Copied into state immediately, because the navigation state is cleared
  // below and would otherwise vanish before the confirmation can render.
  const [justAdded, setJustAdded] = useState<{ id: string; title: string } | null>(
    created.createdId ? { id: created.createdId, title: created.createdTitle ?? '' } : null,
  )

  // Clearing the navigation state and timing the confirmation out are two
  // separate jobs, and they must stay separate. Doing both in one effect meant
  // the navigate() call changed that effect's own dependency, which ran its
  // cleanup, cancelled the timer, and then returned early without setting a
  // new one — so the highlight never cleared at all.
  useEffect(() => {
    if (!created.createdId) return
    // So a refresh or a back-navigation does not re-announce a submission the
    // user has already seen.
    navigate('.', { replace: true, state: null })
  }, [created.createdId, navigate])

  useEffect(() => {
    if (!justAdded) return
    const timer = window.setTimeout(() => setJustAdded(null), CONFIRMATION_MS)
    return () => window.clearTimeout(timer)
  }, [justAdded])
  // The row button that opened the panel, so focus can go back to it.
  const lastTriggerRef = useRef<HTMLButtonElement | null>(null)

  const load = useCallback(async (status: string) => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.listSubmissions(status))
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load your submissions.')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(filter)
  }, [filter, load])

  // Selection survives a filter change or a refresh, as long as the row is
  // still in view — returning from details should not lose your place.
  const selected = data?.results.find((row) => row.id === selectedId) ?? null

  return (
    <AppShell
      nav={[
        {
          to: '/submissions',
          label: 'My submissions',
          icon: 'document',
          count: data?.counts.all,
          end: true,
        },
      ]}
    >
      <div className="page-head">
        <div>
          <h1 className="page-title">My submissions</h1>
          <p className="page-head__sub">Track what you have sent and read reviewer feedback.</p>
        </div>
        <Link className="btn btn--primary" to="/submissions/new">
          <Icon name="plus" size={18} />
          New submission
        </Link>
      </div>

      <div className="toolbar">
        {FILTERS.map((item) => (
          <button
            key={item.key}
            type="button"
            className="chip"
            aria-pressed={filter === item.key}
            onClick={() => setFilter(item.key)}
          >
            {item.label}
            {data && <span className="chip__count">{data.counts[item.key] ?? 0}</span>}
          </button>
        ))}
        <span className="toolbar__spacer" />
        <button type="button" className="btn" onClick={() => void load(filter)} disabled={loading}>
          <Icon name="refresh" size={16} />
          Refresh
        </button>
      </div>

      {justAdded && (
        <div role="status" className="notice notice--success">
          <Icon name="check-circle" />
          <div className="notice__body">
            <p>
              <strong>{justAdded.title}</strong> was submitted for review. A reviewer will
              approve or reject it.
            </p>
          </div>
        </div>
      )}

      {loading && <TableSkeleton />}
      {!loading && error && <ErrorNotice message={error} onRetry={() => void load(filter)} />}

      {!loading && !error && data?.results.length === 0 && (
        <EmptyState
          title={filter === 'all' ? 'Nothing submitted yet' : `No ${filter} submissions`}
          hint={
            filter === 'all'
              ? 'Send a PDF for review and its status will appear here.'
              : 'Try a different filter.'
          }
          action={
            filter === 'all' ? (
              <Link className="btn btn--primary" to="/submissions/new">
                <Icon name="plus" size={18} />
                New submission
              </Link>
            ) : undefined
          }
        />
      )}

      {/* The split column is only applied when a panel is actually shown.
          Reserving it unconditionally squeezes the table beside empty space. */}
      {!loading && !error && data && data.results.length > 0 && (
        <div className={selected ? 'layout-split' : undefined}>
          {/* The card wraps the table only — its height follows the rows, so
              there is no large empty bordered area under a short list. */}
          <div className="card table-wrap">
            <table className="table">
              <caption className="sr-only">
                Your submissions, newest first. Select a row to read its details.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Document</th>
                  <th scope="col">Status</th>
                  <th scope="col">Submitted</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((row) => (
                  <tr
                    key={row.id}
                    className={
                      [
                        row.id === selectedId ? 'row--selected' : '',
                        row.id === justAdded?.id ? 'row--just-added' : '',
                      ]
                        .filter(Boolean)
                        .join(' ') || undefined
                    }
                    data-clickable="true"
                    onClick={(event) => {
                      if (shouldIgnoreRowClick(event)) return
                      // Focus returns to this row's title button when the
                      // panel closes, wherever in the row the click landed.
                      lastTriggerRef.current =
                        event.currentTarget.querySelector('button')
                      setSelectedId(row.id)
                    }}
                  >
                    <td>
                      <div className="doc-cell">
                        <span className="doc-cell__icon">
                          <Icon name="document" size={18} />
                        </span>
                        <span className="doc-cell__text">
                          <button
                            type="button"
                            className="doc-cell__title truncate"
                            aria-current={row.id === selectedId ? 'true' : undefined}
                            onClick={(event) => {
                              lastTriggerRef.current = event.currentTarget
                              setSelectedId(row.id)
                            }}
                          >
                            {row.title}
                          </button>
                          <div className="small faint truncate">{row.original_filename}</div>
                        </span>
                      </div>
                    </td>
                    <td data-label="Status">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="small muted" data-label="Submitted">{formatDate(row.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {selected && (
            <DetailPanel
              submission={selected}
              onClose={() => {
                setSelectedId(null)
                lastTriggerRef.current?.focus()
              }}
            />
          )}
        </div>
      )}
    </AppShell>
  )
}

function DetailPanel({ submission, onClose }: { submission: Submission; onClose: () => void }) {
  const [opening, setOpening] = useState(false)
  const [urlError, setUrlError] = useState<string | null>(null)
  const panelRef = useRef<HTMLElement>(null)

  // On narrow screens this panel covers the page, so it must behave like one:
  // focus moves into it when it opens, Escape dismisses it, and the caller
  // returns focus to the row that opened it.
  useEffect(() => {
    panelRef.current?.focus()
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose, submission.id])

  async function openPdf() {
    setOpening(true)
    setUrlError(null)
    try {
      // Fetched fresh every time: these links expire, so a cached one would
      // fail later for no reason the user could understand.
      const { url } = await api.getFileUrl(submission.id)
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (caught) {
      setUrlError(caught instanceof ApiError ? caught.message : 'Could not open the document.')
    } finally {
      setOpening(false)
    }
  }

  return (
    <aside
      ref={panelRef}
      className="card panel panel--overlay"
      aria-label={`Details for ${submission.title}`}
      tabIndex={-1}
    >
      <div className="panel__head">
        <div style={{ minWidth: 0 }}>
          <h2 className="panel__title">{submission.title}</h2>
          <div style={{ marginTop: 'var(--s1)' }}>
            <StatusBadge status={submission.status} />
          </div>
        </div>
        <button type="button" className="btn btn--ghost btn--icon" onClick={onClose}>
          <Icon name="close" size={18} />
          <span className="sr-only">Close details</span>
        </button>
      </div>

      <div className="panel__section">
        <dl className="meta-list">
          <dt>File</dt>
          <dd className="truncate">{submission.original_filename}</dd>
          <dt>Size</dt>
          <dd>{formatSize(submission.file_size_bytes)}</dd>
        </dl>
        <button
          type="button"
          className="btn"
          style={{ marginTop: 'var(--s2)', width: '100%' }}
          onClick={() => void openPdf()}
          disabled={opening}
        >
          <Icon name="external" size={16} />
          {opening ? 'Opening…' : submission.content_type.startsWith('image/') ? 'Open image' : 'Open PDF'}
        </button>
        {urlError && (
          <div style={{ marginTop: 'var(--s1)' }}>
            <ErrorNotice message={urlError} />
          </div>
        )}
      </div>

      {submission.context && (
        <div className="panel__section">
          <h3 className="section-title">Your context</h3>
          <p className="muted" style={{ marginBottom: 0 }}>
            {submission.context}
          </p>
        </div>
      )}

      {submission.status !== 'pending' && (
        <div className="panel__section">
          <h3 className="section-title">Reviewer feedback</h3>
          {submission.decision_note ? (
            <p style={{ marginBottom: 4 }}>{submission.decision_note}</p>
          ) : (
            <p className="faint" style={{ marginBottom: 4 }}>
              No note was left.
            </p>
          )}
          <p className="small faint" style={{ margin: 0 }}>
            {submission.reviewed_by?.display_name ?? 'A reviewer'} ·{' '}
            {formatDate(submission.reviewed_at)}
          </p>
        </div>
      )}

      {submission.status === 'pending' && (
        <div className="panel__section">
          <div className="notice notice--warning" style={{ marginBottom: 0 }}>
            <Icon name="clock" />
            <div className="notice__body">
              <p>Waiting for a reviewer. You will see their decision here.</p>
            </div>
          </div>
        </div>
      )}

      <div className="panel__section">
        <h3 className="section-title" style={{ marginBottom: 'var(--s2)' }}>
          Activity
        </h3>
        <ActivityTrail
          createdAt={submission.created_at}
          submitter={submission.submitted_by.display_name}
          status={submission.status}
          reviewedAt={submission.reviewed_at}
          reviewer={submission.reviewed_by?.display_name ?? null}
        />
      </div>
    </aside>
  )
}
