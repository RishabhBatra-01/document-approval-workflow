import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api, ApiError, type Identity } from './api'
import { supabase } from './supabase'

type SessionState =
  | { phase: 'loading' }
  | { phase: 'signed-out' }
  | { phase: 'signed-in'; identity: Identity }
  /** Authenticated with Supabase but not provisioned here, or Auth is down. */
  | { phase: 'blocked'; code: string; message: string }

interface SessionValue {
  state: SessionState
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

const SessionContext = createContext<SessionValue | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ phase: 'loading' })

  const loadIdentity = useCallback(async () => {
    const { data } = await supabase.auth.getSession()
    if (!data.session) {
      setState({ phase: 'signed-out' })
      return
    }
    try {
      const identity = await api.me()
      setState({ phase: 'signed-in', identity })
    } catch (error) {
      if (error instanceof ApiError) {
        // An expired or invalid token is not an account problem — it is a
        // lapsed session, and the only sensible answer is the sign-in page.
        // Reporting it as "Account unavailable" told people their account was
        // broken when they had simply been away for an hour.
        if (error.status === 401 || error.code === 'no_session') {
          await supabase.auth.signOut().catch(() => {})
          setState({ phase: 'signed-out' })
          return
        }
        // Everything else — chiefly an authenticated user with no application
        // profile — genuinely is blocked, and must not reach a protected
        // screen.
        setState({ phase: 'blocked', code: error.code, message: error.message })
        return
      }
      setState({ phase: 'blocked', code: 'unknown', message: 'Could not load your account.' })
    }
  }, [])

  useEffect(() => {
    void loadIdentity()
    const { data: listener } = supabase.auth.onAuthStateChange((event) => {
      if (event === 'SIGNED_OUT') {
        setState({ phase: 'signed-out' })
      } else if (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') {
        void loadIdentity()
      }
    })
    return () => listener.subscription.unsubscribe()
  }, [loadIdentity])

  const signIn = useCallback(
    async (email: string, password: string) => {
      const { error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) throw new Error('Email or password is incorrect.')
      await loadIdentity()
    },
    [loadIdentity],
  )

  const signOut = useCallback(async () => {
    await supabase.auth.signOut()
    // Drop every trace of the previous account so the next person to sign in
    // on this browser cannot see cached data from the last one.
    setState({ phase: 'signed-out' })
  }, [])

  const value = useMemo(() => ({ state, signIn, signOut }), [state, signIn, signOut])
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used inside SessionProvider')
  return value
}
