import type { Status } from '../lib/api'
import { Icon, type IconName } from './Icon'

const STATUS_META: Record<Status, { label: string; icon: IconName }> = {
  pending: { label: 'Pending', icon: 'clock' },
  approved: { label: 'Approved', icon: 'check-circle' },
  rejected: { label: 'Rejected', icon: 'x-circle' },
}

/** Status carries a word and a shape, never colour alone. */
export function StatusBadge({ status }: { status: Status }) {
  const meta = STATUS_META[status]
  return (
    <span className={`badge badge--${status}`}>
      <Icon name={meta.icon} size={15} />
      {meta.label}
    </span>
  )
}

/** A shape of the real thing, so the layout does not jump when data lands. */
export function TableSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="card" style={{ padding: 'var(--s2)' }} role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={index}
          style={{
            display: 'flex',
            gap: 'var(--s2)',
            alignItems: 'center',
            padding: '12px 0',
            borderBottom: index === rows - 1 ? 'none' : '1px solid var(--line)',
          }}
        >
          <div className="skeleton" style={{ width: 36, height: 36, borderRadius: 8 }} />
          <div className="skeleton" style={{ flex: '1 1 auto', maxWidth: 260 }} />
          <div className="skeleton" style={{ width: 92 }} />
          <div className="skeleton" style={{ width: 120 }} />
        </div>
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  )
}

export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="notice notice--error">
      <Icon name="alert" />
      <div className="notice__body">
        <p>{message}</p>
        {onRetry && (
          <button
            type="button"
            className="btn"
            style={{ marginTop: 'var(--s1)' }}
            onClick={onRetry}
          >
            <Icon name="refresh" size={16} />
            Try again
          </button>
        )}
      </div>
    </div>
  )
}

/** An empty result and a failed request must never look the same. */
export function EmptyState({
  icon = 'document',
  title,
  hint,
  action,
}: {
  icon?: IconName
  title: string
  hint?: string
  action?: React.ReactNode
}) {
  return (
    <div className="card empty">
      <span className="empty__icon">
        <Icon name={icon} size={36} />
      </span>
      <p style={{ margin: 0, fontWeight: 600, color: 'var(--ink)' }}>{title}</p>
      {hint && <p style={{ margin: 0 }}>{hint}</p>}
      {action}
    </div>
  )
}

export function ActivityTrail({
  createdAt,
  submitter,
  status,
  reviewedAt,
  reviewer,
}: {
  createdAt: string
  submitter: string
  status: Status
  reviewedAt: string | null
  reviewer: string | null
}) {
  const decided = status !== 'pending' && reviewedAt
  return (
    <ul className="activity">
      {decided && (
        <li className="activity__item">
          <span className={`activity__dot activity__dot--${status}`}>
            <Icon name={status === 'approved' ? 'check-circle' : 'x-circle'} size={14} />
          </span>
          <span>
            <strong>{status === 'approved' ? 'Approved' : 'Rejected'}</strong>
            <br />
            {/* The actor is only named when the API supplied one. */}
            <span className="small faint">
              {reviewer ? `${reviewer} · ` : ''}
              {formatDate(reviewedAt)}
            </span>
          </span>
        </li>
      )}
      <li className="activity__item">
        <span className="activity__dot">
          <Icon name="upload" size={14} />
        </span>
        <span>
          <strong>Submitted</strong>
          <br />
          <span className="small faint">
            {submitter} · {formatDate(createdAt)}
          </span>
        </span>
      </li>
    </ul>
  )
}

export function formatDate(iso: string | null): string {
  if (!iso) return '—'
  // Intl rejects dateStyle/timeStyle combined with timeZoneName, so the
  // components are spelled out. The zone is shown so a reviewer and a
  // submitter in different places read the same instant.
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
  })
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Whether a click on a table row should be ignored.
 *
 * The whole row is clickable, but the row is not the only thing in it. A click
 * is left alone when:
 *
 *  - it landed on a link or button inside the row, which will act for itself —
 *    handling it twice would navigate twice;
 *  - the user is selecting text, so dragging across a name to copy it does not
 *    also open the document;
 *  - a modifier is held, so cmd/ctrl/shift-click keep their normal browser
 *    meaning rather than being hijacked.
 */
export function shouldIgnoreRowClick(event: React.MouseEvent): boolean {
  if (event.defaultPrevented) return true
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return true
  if (event.button !== 0) return true

  const target = event.target as HTMLElement | null
  if (target?.closest('a, button, input, textarea, select, [role="button"]')) return true

  const selection = window.getSelection()
  if (selection && !selection.isCollapsed && selection.toString().trim().length > 0) return true

  return false
}

/**
 * An indeterminate activity indicator.
 *
 * Indeterminate on purpose: the browser cannot measure how far a plain
 * multipart POST has got, and a bar that creeps to 90% and waits is a lie.
 * The accompanying text carries the actual meaning, so under
 * prefers-reduced-motion the spinner is hidden entirely rather than frozen
 * mid-rotation, which looks broken.
 */
export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <span
      className="spinner"
      style={{ width: size, height: size }}
      aria-hidden="true"
    />
  )
}

/** Explains an unusually slow request rather than spinning in silence. */
export function SlowRequestNotice({ message }: { message: string }) {
  return (
    <p role="status" className="small muted" style={{ margin: 'var(--s1) 0 0' }}>
      {message}
    </p>
  )
}
