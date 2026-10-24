import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { api, ApiError, type Submission, type SubmissionList } from '../lib/api'
import { AppShell } from '../components/AppShell'
import { Icon } from '../components/Icon'
import {
  EmptyState,
  ErrorNotice,
  StatusBadge,
  TableSkeleton,
  formatDate,
  shouldIgnoreRowClick,
} from '../components/common'

type Tab = 'pending' | 'reviewed'

export function reviewerNav(counts: Record<string, number> | undefined) {
  return [
    { to: '/review', label: 'Pending reviews', icon: 'inbox' as const, count: counts?.pending, end: true },
    { to: '/review/done', label: 'Reviewed', icon: 'check-circle' as const },
  ]
}

export function ReviewQueue() {
  const navigate = useNavigate()
  // One component serves both tabs; the route decides which.
  const { view } = useParams()
  const tab: Tab = view === 'done' ? 'reviewed' : 'pending'

  const [rows, setRows] = useState<Submission[] | null>(null)
  const [counts, setCounts] = useState<SubmissionList['counts'] | undefined>()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async (which: Tab) => {
    setLoading(true)
    setError(null)
    try {
      if (which === 'pending') {
        const page = await api.listSubmissions('pending')
        setRows(page.results)
        setCounts(page.counts)
      } else {
        // The API filters one status at a time; "Reviewed" is both terminal
        // statuses, so they are merged here and shown newest decision first.
        const [approved, rejected] = await Promise.all([
          api.listSubmissions('approved'),
          api.listSubmissions('rejected'),
        ])
        setCounts(approved.counts)
        setRows(
          [...approved.results, ...rejected.results].sort((a, b) =>
            (b.reviewed_at ?? b.created_at).localeCompare(a.reviewed_at ?? a.created_at),
          ),
        )
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load the queue.')
      setRows(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(tab)
  }, [tab, load])

  const reviewedCount = (counts?.approved ?? 0) + (counts?.rejected ?? 0)

  return (
    <AppShell nav={reviewerNav(counts)}>
      <div className="page-head">
        <div>
          <h1 className="page-title">{tab === 'pending' ? 'Pending reviews' : 'Reviewed'}</h1>
          <p className="page-head__sub">
            {tab === 'pending'
              ? 'Oldest first, so nothing waits indefinitely.'
              : 'Decisions already made. These are final.'}
          </p>
        </div>
      </div>

      <div className="toolbar">
        <Link to="/review" className="chip" aria-current={tab === 'pending' ? 'page' : undefined}>
          Pending
          {counts && <span className="chip__count">{counts.pending ?? 0}</span>}
        </Link>
        <Link to="/review/done" className="chip" aria-current={tab === 'reviewed' ? 'page' : undefined}>
          Reviewed
          {counts && <span className="chip__count">{reviewedCount}</span>}
        </Link>
        <span className="toolbar__spacer" />
        <button type="button" className="btn" onClick={() => void load(tab)} disabled={loading}>
          <Icon name="refresh" size={16} />
          Refresh
        </button>
      </div>

      {loading && <TableSkeleton />}
      {!loading && error && <ErrorNotice message={error} onRetry={() => void load(tab)} />}

      {/* An empty queue is good news; a failed request is not. They look
          different on purpose. */}
      {!loading && !error && rows?.length === 0 && (
        <EmptyState
          icon={tab === 'pending' ? 'check-circle' : 'inbox'}
          title={tab === 'pending' ? 'Nothing waiting for review' : 'Nothing reviewed yet'}
          hint={
            tab === 'pending'
              ? 'New submissions will appear here.'
              : 'Decisions you make will be listed here.'
          }
        />
      )}

      {!loading && !error && rows && rows.length > 0 && (
        <div className="card table-wrap enter" key={`${tab}-${rows.length}`}>
          <table className="table">
            <caption className="sr-only">
              {tab === 'pending' ? 'Submissions waiting for a decision' : 'Submissions already decided'}
            </caption>
            <thead>
              <tr>
                <th scope="col">Document</th>
                <th scope="col">Submitted by</th>
                <th scope="col">Status</th>
                <th scope="col">{tab === 'pending' ? 'Waiting since' : 'Decided'}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  data-clickable="true"
                  onClick={(event) => {
                    if (shouldIgnoreRowClick(event)) return
                    navigate(`/review/document/${row.id}`)
                  }}
                >
                  <td>
                    <div className="doc-cell">
                      <span className="doc-cell__icon">
                        <Icon name="document" size={18} />
                      </span>
                      <span className="doc-cell__text">
                        <Link className="doc-cell__title truncate" to={`/review/document/${row.id}`}>
                          {row.title}
                        </Link>
                        <div className="small faint truncate">{row.original_filename}</div>
                      </span>
                    </div>
                  </td>
                  <td className="truncate" data-label="Submitted by">{row.submitted_by.display_name}</td>
                  <td data-label="Status">
                    <StatusBadge status={row.status} />
                  </td>
                  <td className="small muted" data-label={tab === 'pending' ? 'Waiting since' : 'Decided'}>
                    {formatDate(tab === 'pending' ? row.created_at : row.reviewed_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AppShell>
  )
}
