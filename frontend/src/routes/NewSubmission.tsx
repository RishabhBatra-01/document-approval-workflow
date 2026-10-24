import { useRef, useState, type DragEvent, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { api, ApiError } from '../lib/api'
import { AppShell } from '../components/AppShell'
import { Icon } from '../components/Icon'
import { ErrorNotice, SlowRequestNotice, Spinner, formatSize } from '../components/common'
import { SLOW_REQUEST_MS, SPINNER_DELAY_MS, useDelayedFlag } from '../lib/pending'

const MAX_BYTES = 5 * 1024 * 1024
const MAX_TITLE = 150
const MAX_CONTEXT = 2000

export function NewSubmission() {
  const navigate = useNavigate()
  const fileInput = useRef<HTMLInputElement>(null)

  const [title, setTitle] = useState('')
  const [context, setContext] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const [submitting, setSubmitting] = useState(false)

  const showSpinner = useDelayedFlag(submitting, SPINNER_DELAY_MS)
  const showSlowHint = useDelayedFlag(submitting, SLOW_REQUEST_MS)

  const oversize = file !== null && file.size > MAX_BYTES

  function choose(next: File | null) {
    setFile(next)
    setFieldErrors({})
  }

  function onDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    const dropped = event.dataTransfer.files?.[0]
    if (dropped) choose(dropped)
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!file) {
      setFieldErrors({ file: ['Choose a PDF to submit.'] })
      return
    }
    setSubmitting(true)
    setError(null)
    setFieldErrors({})
    try {
      const created = await api.createSubmission({
        title: title.trim(),
        context: context.trim(),
        file,
      })
      // The list confirms the submission rather than silently showing a new
      // row: the anxious moment is right after submitting, not during.
      navigate('/submissions', { state: { createdId: created.id, createdTitle: created.title } })
    } catch (caught) {
      // Nothing is cleared. The title, the context and the chosen file all
      // survive a failure, so a retry costs no retyping.
      if (caught instanceof ApiError) {
        setError(caught.message)
        setFieldErrors(caught.fieldErrors)
      } else {
        setError('Could not submit. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AppShell nav={[{ to: '/submissions', label: 'My submissions', icon: 'document', end: true }]}>
      <Link className="breadcrumb" to="/submissions">
        <Icon name="chevron-left" size={18} />
        My submissions
      </Link>

      <div className="page-head">
        <div>
          <h1 className="page-title">New submission</h1>
          <p className="page-head__sub">
            One file per submission. A reviewer will approve or reject it.
          </p>
        </div>
      </div>

      <form onSubmit={onSubmit} noValidate style={{ maxWidth: 680 }}>
        {error && <ErrorNotice message={error} />}

        <div className="card" style={{ padding: 'var(--s3)' }}>
          <div className="field">
            <label htmlFor="title">Title</label>
            <input
              id="title"
              type="text"
              required
              maxLength={MAX_TITLE}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              aria-describedby={fieldErrors.title ? 'title-error' : undefined}
              aria-invalid={fieldErrors.title ? true : undefined}
            />
            {fieldErrors.title && (
              <p id="title-error" role="alert" className="field__error">
                {fieldErrors.title.join(' ')}
              </p>
            )}
          </div>

          <div className="field">
            <label htmlFor="context">Context</label>
            <p className="field__hint small" id="context-help">
              Optional. Anything the reviewer should know before reading.
            </p>
            <textarea
              id="context"
              rows={4}
              maxLength={MAX_CONTEXT}
              value={context}
              aria-describedby="context-help context-count"
              onChange={(event) => setContext(event.target.value)}
            />
            <p id="context-count" className="small faint" style={{ margin: '6px 0 0' }}>
              {context.length} of {MAX_CONTEXT} characters
            </p>
          </div>

          <div className="field" style={{ marginBottom: 0 }}>
            <span className="label" id="file-label">
              Document
            </span>
            <p className="field__hint small" id="file-help">
              PDF, PNG, JPEG or WebP, up to 5 MiB. Password-protected PDFs cannot be
              reviewed. Word, Excel and PowerPoint files need exporting to PDF first.
            </p>

            {!file ? (
              <div
                className={dragging ? 'dropzone dropzone--over' : 'dropzone'}
                onDragOver={(event) => {
                  event.preventDefault()
                  setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
              >
                <Icon name="upload" size={28} />
                <p className="muted" style={{ margin: 'var(--s1) 0' }}>
                  Drag a file here, or choose one.
                </p>
                {/* A real file input, always. Drag-and-drop is an addition to
                    it, never a replacement — it is unusable by keyboard. */}
                <input
                  id="file"
                  ref={fileInput}
                  type="file"
                  accept="application/pdf,image/png,image/jpeg,image/webp,.pdf,.png,.jpg,.jpeg,.webp"
                  aria-labelledby="file-label"
                  aria-describedby="file-help"
                  onChange={(event) => choose(event.target.files?.[0] ?? null)}
                />
              </div>
            ) : (
              <div className="file-card">
                <span className="doc-cell__icon">
                  <Icon name="document" size={18} />
                </span>
                <span className="file-card__text">
                  <strong className="truncate" style={{ display: 'block' }}>
                    {file.name}
                  </strong>
                  <span className="small faint">{formatSize(file.size)}</span>
                  {oversize && (
                    <p role="alert" className="field__error small">
                      This file is over the 5 MiB limit.
                    </p>
                  )}
                </span>
                <span className="file-card__actions">
                  <button
                    type="button"
                    className="btn"
                    onClick={() => fileInput.current?.click()}
                    disabled={submitting}
                  >
                    Replace
                  </button>
                  <button
                    type="button"
                    className="btn btn--icon"
                    onClick={() => {
                      choose(null)
                      if (fileInput.current) fileInput.current.value = ''
                    }}
                    disabled={submitting}
                  >
                    <Icon name="trash" size={16} />
                    <span className="sr-only">Remove {file.name}</span>
                  </button>
                </span>
                <input
                  ref={fileInput}
                  type="file"
                  accept="application/pdf,image/png,image/jpeg,image/webp,.pdf,.png,.jpg,.jpeg,.webp"
                  className="sr-only"
                  aria-labelledby="file-label"
                  onChange={(event) => choose(event.target.files?.[0] ?? null)}
                />
              </div>
            )}

            {fieldErrors.file && (
              <p role="alert" className="field__error">
                {fieldErrors.file.join(' ')}
              </p>
            )}
          </div>
        </div>

        <div className="toolbar" style={{ marginTop: 'var(--s3)' }}>
          <button
            type="submit"
            className="btn btn--primary btn--steady"
            disabled={submitting || !title.trim() || !file || oversize}
          >
            {/* A plain multipart POST reports no measured progress, so none is
                invented. This says what is true: it is uploading. The button
                keeps its width so the layout does not jump mid-action. */}
            {showSpinner && <Spinner />}
            {submitting ? 'Uploading…' : 'Submit for review'}
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => navigate('/submissions')}
            disabled={submitting}
          >
            Cancel
          </button>
        </div>

        {showSlowHint && (
          <SlowRequestNotice message="Still uploading — the server may be waking up. This can take up to a minute on free hosting." />
        )}
      </form>
    </AppShell>
  )
}
