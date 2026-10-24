import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { SessionProvider, useSession } from './lib/session'
import { Icon } from './components/Icon'
import { Login } from './routes/Login'
import { MySubmissions } from './routes/MySubmissions'
import { NewSubmission } from './routes/NewSubmission'
import { ReviewDetail } from './routes/ReviewDetail'
import { ReviewQueue } from './routes/ReviewQueue'
import type { Role } from './lib/api'

function landingFor(role: Role): string {
  return role === 'reviewer' ? '/review' : '/submissions'
}

/** A quiet full-page state, used while identity is still unknown. */
function Waiting({ message }: { message: string }) {
  return (
    <main className="standalone">
      <p role="status" className="muted">
        {message}
      </p>
    </main>
  )
}

/**
 * Route guarding is usability, not security: the backend re-checks the role on
 * every request, so typing a URL directly gains nothing. Its job here is to
 * avoid showing a screen the user cannot use.
 */
function Guard({ allow, children }: { allow: Role; children: React.ReactNode }) {
  const { state, signOut } = useSession()

  // Protected content must never flash before the identity is known.
  if (state.phase === 'loading') return <Waiting message="Loading your account…" />
  if (state.phase === 'signed-out') return <Navigate to="/login" replace />

  if (state.phase === 'blocked') {
    return (
      <main className="standalone">
        <div className="card standalone__card">
          <div className="standalone__brand">
            <Icon name="alert" size={24} />
            <span>Account unavailable</span>
          </div>
          <p role="alert">{state.message}</p>
          <button
            type="button"
            className="btn"
            style={{ marginTop: 'var(--s2)' }}
            onClick={() => void signOut()}
          >
            <Icon name="sign-out" size={16} />
            Sign out
          </button>
        </div>
      </main>
    )
  }

  if (state.identity.role !== allow) return <Navigate to={landingFor(state.identity.role)} replace />
  return <>{children}</>
}

function Root() {
  const { state } = useSession()
  if (state.phase === 'loading') return <Waiting message="Loading…" />
  if (state.phase === 'signed-in') return <Navigate to={landingFor(state.identity.role)} replace />
  return <Navigate to="/login" replace />
}

function LoginRoute() {
  const { state } = useSession()
  if (state.phase === 'loading') return <Waiting message="Loading…" />
  // Already signed in: send them on rather than showing the form again.
  if (state.phase === 'signed-in') return <Navigate to={landingFor(state.identity.role)} replace />
  return <Login />
}

export function App() {
  return (
    <SessionProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Root />} />
          <Route path="/login" element={<LoginRoute />} />

          <Route
            path="/submissions"
            element={
              <Guard allow="submitter">
                <MySubmissions />
              </Guard>
            }
          />
          <Route
            path="/submissions/new"
            element={
              <Guard allow="submitter">
                <NewSubmission />
              </Guard>
            }
          />

          <Route
            path="/review"
            element={
              <Guard allow="reviewer">
                <ReviewQueue />
              </Guard>
            }
          />
          <Route
            path="/review/:view"
            element={
              <Guard allow="reviewer">
                <ReviewQueue />
              </Guard>
            }
          />
          <Route
            path="/review/document/:id"
            element={
              <Guard allow="reviewer">
                <ReviewDetail />
              </Guard>
            }
          />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </SessionProvider>
  )
}
