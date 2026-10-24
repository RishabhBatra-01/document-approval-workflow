import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY

if (!url || !publishableKey) {
  throw new Error(
    'Missing VITE_SUPABASE_URL or VITE_SUPABASE_PUBLISHABLE_KEY. Copy frontend/.env.example to frontend/.env.local.',
  )
}

/**
 * The browser's Supabase client handles ONE thing: the user's session.
 *
 * It never reads or writes application data — the Data API is disabled and the
 * storage bucket is private, so this client's key grants nothing on its own.
 * Every piece of application data comes from our Django API, which re-checks
 * authorization on every request.
 */
export const supabase = createClient(url, publishableKey, {
  auth: { persistSession: true, autoRefreshToken: true },
})
