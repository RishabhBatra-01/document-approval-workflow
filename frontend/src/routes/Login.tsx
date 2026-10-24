import { useState, type FormEvent } from 'react'
import { Icon, type IconName } from '../components/Icon'
import { Logo } from '../components/Logo'
import { ErrorNotice, Spinner } from '../components/common'
import { SPINNER_DELAY_MS, useDelayedFlag } from '../lib/pending'
import { useSession } from '../lib/session'

/**
 * How the product actually works, in three steps.
 *
 * This is description, not decoration: every step is something the product
 * genuinely does. Nothing here hints at a feature that does not exist, which
 * rules out the usual login-page filler — testimonials, statistics, logos of
 * companies that do not use it.
 */
const STEPS: { icon: IconName; title: string; detail: string }[] = [
  { icon: 'upload', title: 'Submit', detail: 'Send a PDF with any context a reviewer needs.' },
  { icon: 'inbox', title: 'Review', detail: 'A reviewer reads it and decides.' },
  { icon: 'check-circle', title: 'Decision', detail: 'You see the outcome and their feedback.' },
]

export function Login() {
  const { signIn } = useSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const showSpinner = useDelayedFlag(busy, SPINNER_DELAY_MS)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await signIn(email.trim(), password)
      // Where to go next is decided in one place, from the verified role.
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not sign in.')
      setPassword('') // only the password is cleared; the email is kept
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      {/* The brand side carries the product's own colour, so signing in looks
          like the same application you are about to enter. */}
      <section className="auth__brand-panel">
        <Logo className="auth__watermark" size={520} />

        <div className="auth__brand-content">
          <div className="auth__wordmark">
            <Logo size={30} />
            <span>Document Review</span>
          </div>

          <h2 className="auth__headline">
            Send a document for approval, and know where it stands.
          </h2>

          <ol className="auth__steps">
            {STEPS.map((step, index) => (
              <li key={step.title} className="auth__step">
                <span className="auth__step-icon">
                  <Icon name={step.icon} size={18} />
                </span>
                <span>
                  <strong>
                    {index + 1}. {step.title}
                  </strong>
                  <span className="auth__step-detail">{step.detail}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="auth__form-panel">
        <div className="auth__form">
          {/* Shown only on narrow screens, where the brand panel is hidden. */}
          <div className="auth__wordmark auth__wordmark--compact">
            <Logo size={26} />
            <span>Document Review</span>
          </div>

          <h1 className="page-title auth__title">Sign in</h1>
          <p className="muted auth__subtitle">Use the account you were given.</p>

          <form onSubmit={onSubmit} noValidate>
            {error && <ErrorNotice message={error} />}

            <div className="field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                required
                autoFocus
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>

            <button
              type="submit"
              className="btn btn--primary btn--block"
              disabled={busy || !email || !password}
            >
              {showSpinner && <Spinner />}
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          {/* There is no sign-up or password-reset flow in this version, so
              saying so is kinder than leaving someone hunting for a link that
              was never there. */}
          <p className="small faint auth__footnote">
            Accounts are created by an administrator. If you cannot sign in, contact them.
          </p>
        </div>
      </section>
    </div>
  )
}
