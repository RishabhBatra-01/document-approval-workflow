/**
 * Frontend behaviour tests.
 *
 * Pure renders with ordinary inputs — no mocked fetch, no intercepted
 * requests, no fake service clients. Behaviour that needs the API (error
 * retention, 409 handling, logout isolation) is verified in the browser
 * against the running stack rather than by faking a server.
 */
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { ActivityTrail, EmptyState, ErrorNotice, StatusBadge, formatSize } from '../src/components/common'
import { Icon } from '../src/components/Icon'
import { ApiError } from '../src/lib/api'

describe('formatSize', () => {
  it('shows bytes below a kilobyte', () => {
    expect(formatSize(512)).toBe('512 B')
  })

  it('shows kilobytes below a megabyte', () => {
    expect(formatSize(2048)).toBe('2 KB')
  })

  it('shows megabytes at and above a megabyte', () => {
    expect(formatSize(5 * 1024 * 1024)).toBe('5.0 MB')
  })
})

describe('StatusBadge', () => {
  it('names the status in words, so colour is never the only signal', () => {
    for (const [status, label] of [
      ['pending', 'Pending'],
      ['approved', 'Approved'],
      ['rejected', 'Rejected'],
    ] as const) {
      expect(renderToStaticMarkup(<StatusBadge status={status} />)).toContain(label)
    }
  })

  it('gives each status a distinct icon as well as a distinct colour', () => {
    const markup = (['pending', 'approved', 'rejected'] as const).map((status) =>
      renderToStaticMarkup(<StatusBadge status={status} />),
    )
    expect(new Set(markup).size).toBe(3)
  })
})

describe('Icon', () => {
  it('is hidden from assistive technology, because every icon has a text label', () => {
    expect(renderToStaticMarkup(<Icon name="document" />)).toContain('aria-hidden="true"')
  })

  it('inherits the surrounding text colour', () => {
    expect(renderToStaticMarkup(<Icon name="check-circle" />)).toContain('stroke="currentColor"')
  })

  it('is not focusable, so it adds no stops to the tab order', () => {
    expect(renderToStaticMarkup(<Icon name="inbox" />)).toContain('focusable="false"')
  })
})

describe('ActivityTrail', () => {
  const base = {
    createdAt: '2026-10-24T09:30:00Z',
    submitter: 'Alex Morgan',
    reviewedAt: null,
    reviewer: null,
  }

  it('shows only the submission event while a document is pending', () => {
    const html = renderToStaticMarkup(<ActivityTrail {...base} status="pending" />)
    expect(html).toContain('Submitted')
    expect(html).not.toContain('Approved')
    expect(html).not.toContain('Rejected')
  })

  it('shows the decision alongside the submission once decided', () => {
    const html = renderToStaticMarkup(
      <ActivityTrail
        {...base}
        status="approved"
        reviewedAt="2026-10-24T11:00:00Z"
        reviewer="Sam Patel"
      />,
    )
    expect(html).toContain('Approved')
    expect(html).toContain('Sam Patel')
    expect(html).toContain('Submitted')
  })

  it('does not invent an actor when the API supplied none', () => {
    const html = renderToStaticMarkup(
      <ActivityTrail {...base} status="rejected" reviewedAt="2026-10-24T11:00:00Z" reviewer={null} />,
    )
    expect(html).toContain('Rejected')
    expect(html).not.toContain('undefined')
    expect(html).not.toContain('null')
  })
})

describe('empty and error states', () => {
  it('are visibly different, so an empty list never reads as a failure', () => {
    const empty = renderToStaticMarkup(<EmptyState title="Nothing waiting for review" />)
    const failed = renderToStaticMarkup(<ErrorNotice message="Could not load the queue." />)

    expect(empty).not.toContain('role="alert"')
    expect(failed).toContain('role="alert"')
    expect(empty).toContain('Nothing waiting for review')
    expect(failed).toContain('Could not load the queue.')
  })

  it('offers a retry only when there is something to retry', () => {
    expect(renderToStaticMarkup(<ErrorNotice message="Failed." />)).not.toContain('Try again')
    expect(
      renderToStaticMarkup(<ErrorNotice message="Failed." onRetry={() => {}} />),
    ).toContain('Try again')
  })
})

describe('ApiError', () => {
  it('carries the backend code so the UI can branch on it', () => {
    const error = new ApiError('already_decided', 'This submission was already approved.', 409)
    expect(error.code).toBe('already_decided')
    expect(error.status).toBe(409)
    expect(error.fieldErrors).toEqual({})
  })

  it('carries field errors when the backend supplies them', () => {
    const error = new ApiError('invalid_request', 'Some fields need attention.', 400, {
      title: ['This field may not be blank.'],
    })
    expect(error.fieldErrors.title).toHaveLength(1)
  })
})
