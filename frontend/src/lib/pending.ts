import { useEffect, useState } from 'react'

/**
 * True once `active` has been true continuously for `delayMs`.
 *
 * Used for two things, both about not lying to the user with timing:
 *
 *  - A spinner that appears instantly flickers on fast actions. Approving is a
 *    single database write and often finishes in well under a second; a
 *    spinner that appears and vanishes reads as a glitch. Holding it back
 *    means quick actions show nothing at all.
 *
 *  - A request that is taking unusually long deserves an explanation rather
 *    than an endlessly spinning circle.
 *
 * Returns to false the moment `active` does, so a finished request clears
 * everything immediately.
 */
export function useDelayedFlag(active: boolean, delayMs: number): boolean {
  const [raised, setRaised] = useState(false)

  useEffect(() => {
    if (!active) {
      setRaised(false)
      return
    }
    const timer = window.setTimeout(() => setRaised(true), delayMs)
    return () => window.clearTimeout(timer)
  }, [active, delayMs])

  return raised
}

/** A spinner appears only once an action is slow enough to notice. */
export const SPINNER_DELAY_MS = 250

/**
 * How long to wait before explaining that the server may be asleep.
 *
 * Render's free tier spins a service down after 15 minutes of no traffic and
 * takes roughly a minute to wake. An evaluator's first click will often be
 * that cold start, and a silent spinner for 45 seconds reads as "broken".
 */
export const SLOW_REQUEST_MS = 3000
