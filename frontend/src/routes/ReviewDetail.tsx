import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { api, ApiError, type Submission } from '../lib/api'
import { AppShell } from '../components/AppShell'
import { Icon } from '../components/Icon'
import {
  ActivityTrail,
  ErrorNotice,
  SlowRequestNotice,
  Spinner,
  StatusBadge,
  TableSkeleton,
  formatDate,
  formatSize,
} from '../components/common'
import { SLOW_REQUEST_MS, SPINNER_DELAY_MS, useDelayedFlag } from '../lib/pending'
import { reviewerNav } from './ReviewQueue'

export function ReviewDetail() {
  const { id = '' } = useParams()
  const navigate = useNavigate()

  const [submission, setSubmission] = useState<Submission | null>(null)
  const [fileUrl, setFileUrl] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const [note, setNote] = useState('')
  const [deciding, setDeciding] = useState<'approve' | 'reject' | null>(null)
  const [decisionError, setDecisionError] = useState<string | null>(null)
  const [conflict, setConflict] = useState(false)

  const busy = deciding !== null
  // A spinner only once the wait is long enough to notice, and an explanation
  // only once it is long enough to worry about.
  const showSpinner = useDelayedFlag(busy, SPINNER_DELAY_MS)
  const showSlowHint = useDelayedFlag(busy, SLOW_REQUEST_MS)

  const loadFileUrl = useCallback(async (submissionId: string) => {
    try {
      const { url } = await api.getFileUrl(submissionId)
      setFileUrl(url)
      return url
    } catch {
      // The document still exists; only the preview link failed. The Open PDF
      // button can retry on demand rather than blocking the whole page.
      setFileUrl(null)
      return null
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      // Both requests at once, not one after the other.
      //
      // The signed URL does not depend on the submission body — the server
      // authorises it from the id either way — so waiting for the first before
      // starting the second doubled the time to a usable page. Each round trip
      // to the Supabase region costs roughly half a second.
      //
      // allSettled, not all: a failed preview link must not take the whole
      // page down with it. The document still loads and the Open PDF button
      // can retry.
      const [detail, fileUrl] = await Promise.allSettled([
        api.getSubmission(id),
        api.getFileUrl(id),
      ])

      if (detail.status === 'rejected') throw detail.reason
      setSubmission(detail.value)
      setFileUrl(fileUrl.status === 'fulfilled' ? fileUrl.value.url : null)
    } catch (caught) {
      setLoadError(caught instanceof ApiError ? caught.message : 'Could not load this submission.')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  async function decide(decision: 'approve' | 'reject') {
    if (decision === 'reject' && !note.trim()) {
      setDecisionError('A rejection needs a reason so the submitter knows what to fix.')
      return
    }
    setDeciding(decision)
    setDecisionError(null)
    try {
      setSubmission(await api.decide(id, decision, note.trim()))
      setConflict(false)
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        // Someone decided first. Show what was genuinely saved rather than
        // assuming, and never name an actor the response did not supply.
        setConflict(true)
        setDecisionError(caught.message)
        try {
          setSubmission(await api.getSubmission(id))
        } catch {
          /* keep whatever is on screen */
        }
      } else {
        // The note is kept so the reviewer does not retype it.
        setDecisionError(
          caught instanceof ApiError ? caught.message : 'Could not save your decision.',
        )
      }
    } finally {
      setDeciding(null)
    }
  }

  async function openPdf() {
    // Links expire, so a fresh one is minted rather than reusing the one
    // fetched when the page loaded.
    const url = await loadFileUrl(id)
    if (url) window.open(url, '_blank', 'noopener,noreferrer')
    else setDecisionError('Could not open the document. Please try again.')
  }

  if (loading) {
    return (
      <AppShell nav={reviewerNav(undefined)} defaultCollapsed>
        <TableSkeleton rows={2} />
      </AppShell>
    )
  }

  if (loadError || !submission) {
    return (
      <AppShell nav={reviewerNav(undefined)} defaultCollapsed>
        <ErrorNotice message={loadError ?? 'Not found.'} onRetry={() => void load()} />
        <Link className="btn" to="/review">
          <Icon name="chevron-left" size={16} />
          Back to queue
        </Link>
      </AppShell>
    )
  }

  const decided = submission.status !== 'pending'
  // From the content type the server recorded after reading the bytes — never
  // from the filename, which the submitter controls.
  const isImage = submission.content_type.startsWith('image/')

  return (
    // keyed on the submission so opening another document replays the entrance
    <AppShell nav={reviewerNav(undefined)} defaultCollapsed>
      <div className="enter" key={submission.id}>
      <Link className="breadcrumb" to="/review">
        <Icon name="chevron-left" size={18} />
        Pending reviews
      </Link>

      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <h1 className="page-title">{submission.title}</h1>
          <p className="page-head__sub small">
            Submitted by {submission.submitted_by.display_name} ·{' '}
            {formatDate(submission.created_at)} · {formatSize(submission.file_size_bytes)}
          </p>
        </div>
        <StatusBadge status={submission.status} />
      </div>

      <div className="layout-split">
        <section className="preview" aria-label="Document preview">
          <div className="preview__bar">
            <Icon name="document" size={16} />
            <span className="small truncate">{submission.original_filename}</span>
            <span className="toolbar__spacer" />
            <button type="button" className="btn btn--ghost" onClick={() => void openPdf()}>
              <Icon name="external" size={16} />
              {isImage ? 'Open image' : 'Open PDF'}
            </button>
          </div>
          {/* Browser-native rendering, for both kinds of document. Browsers
              ship a PDF engine and an image decoder and nothing else, which is
              exactly why those are the two formats accepted. No page or zoom
              toolbar is reimplemented — the browser's own is better. */}
          {fileUrl ? (
            isImage ? (
              <img
                src={fileUrl}
                className="preview__frame preview__frame--image"
                alt={`Submitted image: ${submission.title}`}
              />
            ) : (
              <object
                data={fileUrl}
                type="application/pdf"
                className="preview__frame"
                aria-label={`PDF preview of ${submission.title}`}
              >
                <div className="preview__fallback">
                  <p>This browser cannot display PDFs inline.</p>
                  <button type="button" className="btn" onClick={() => void openPdf()}>
                    <Icon name="external" size={16} />
                    Open PDF
                  </button>
                </div>
              </object>
            )
          ) : (
            <div className="preview__fallback">
              <p>The preview could not be loaded.</p>
              <button type="button" className="btn" onClick={() => void openPdf()}>
                <Icon name="refresh" size={16} />
                Try again
              </button>
            </div>
          )}
        </section>

        <aside className="card panel" aria-label="Decision">
          <div className="panel__section">
            <h2 className="panel__title" style={{ fontSize: '1.15rem' }}>
              Review details
            </h2>
            {submission.context ? (
              <p className="muted" style={{ marginTop: 'var(--s1)', marginBottom: 0 }}>
                {submission.context}
              </p>
            ) : (
              <p className="faint" style={{ marginTop: 'var(--s1)', marginBottom: 0 }}>
                The submitter left no additional context.
              </p>
            )}
          </div>

          {decided ? (
            <div className="panel__section">
              <h2 className="section-title" style={{ marginBottom: 'var(--s1)' }}>
                Decision
              </h2>

              {conflict && (
                <div role="alert" className="notice notice--warning">
                  <Icon name="alert" />
                  <div className="notice__body">
                    <p>
                      Another decision was already saved for this submission. What is shown below
                      is the saved outcome.
                    </p>
                  </div>
                </div>
              )}

              <StatusBadge status={submission.status} />
              {submission.decision_note ? (
                <p style={{ marginTop: 'var(--s2)', marginBottom: 4 }}>{submission.decision_note}</p>
              ) : (
                <p className="faint" style={{ marginTop: 'var(--s2)', marginBottom: 4 }}>
                  No note was left.
                </p>
              )}
              <p className="small faint" style={{ margin: 0 }}>
                {submission.reviewed_by?.display_name ?? 'A reviewer'} ·{' '}
                {formatDate(submission.reviewed_at)}
              </p>

              <button
                type="button"
                className="btn"
                style={{ marginTop: 'var(--s3)', width: '100%' }}
                onClick={() => navigate('/review')}
              >
                <Icon name="chevron-left" size={16} />
                Back to queue
              </button>
            </div>
          ) : (
            <div className="panel__section">
              <h2 className="section-title">Your decision</h2>

              {decisionError && <ErrorNotice message={decisionError} />}

              <div className="field" style={{ marginBottom: 0, marginTop: 'var(--s2)' }}>
                <label htmlFor="note">
                  Feedback to {submission.submitted_by.display_name.split(' ')[0]}
                </label>
                <p className="field__hint small" id="note-help">
                  Required when rejecting. Optional when approving.
                </p>
                <textarea
                  id="note"
                  rows={5}
                  maxLength={2000}
                  value={note}
                  aria-describedby="note-help"
                  onChange={(event) => setNote(event.target.value)}
                  disabled={busy}
                />
              </div>

              <div className="decision-actions">
                {/* Both controls disable together while a request is in
                    flight, so a double click cannot send two decisions. Only
                    the button that was actually pressed reports progress. */}
                <button
                  type="button"
                  className="btn btn--primary btn--steady-sm"
                  disabled={busy}
                  onClick={() => void decide('approve')}
                >
                  {deciding === 'approve' && showSpinner ? (
                    <Spinner />
                  ) : (
                    <Icon name="check-circle" size={16} />
                  )}
                  {deciding === 'approve' ? 'Approving…' : 'Approve'}
                </button>
                <button
                  type="button"
                  className="btn btn--danger btn--steady-sm"
                  disabled={busy}
                  onClick={() => void decide('reject')}
                >
                  {deciding === 'reject' && showSpinner ? (
                    <Spinner />
                  ) : (
                    <Icon name="x-circle" size={16} />
                  )}
                  {deciding === 'reject' ? 'Rejecting…' : 'Reject'}
                </button>
              </div>

              {showSlowHint && (
                <SlowRequestNotice message="Still saving — the server may be waking up. This can take up to a minute on free hosting." />
              )}
            </div>
          )}

          <div className="panel__section">
            <h2 className="section-title" style={{ marginBottom: 'var(--s2)' }}>
              Activity
            </h2>
            <ActivityTrail
              createdAt={submission.created_at}
              submitter={submission.submitted_by.display_name}
              status={submission.status}
              reviewedAt={submission.reviewed_at}
              reviewer={submission.reviewed_by?.display_name ?? null}
            />
          </div>
        </aside>
      </div>
      </div>
    </AppShell>
  )
}
