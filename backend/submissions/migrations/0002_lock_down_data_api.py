"""Close the Data API's access to this application's tables.

Supabase grants the `anon` and `authenticated` roles full privileges on new
tables in the `public` schema by default. Django's migrations create tables
there, so on a fresh project every application table was reachable through the
auto-generated REST API using only the publishable key — the key that ships
inside the JavaScript bundle.

Measured on this project before this migration: `anon` held SELECT, INSERT,
UPDATE, DELETE and TRUNCATE on `app_profile` and `app_submission`. That allows
reading every submission, deleting all of them, and — worst — updating
`app_profile.role` to grant oneself reviewer access, which defeats every
authorization check in the application.

Django connects as the table owner, which is exempt from row-level security
and unaffected by these revocations, so the application keeps working.

This is defence in depth, not a substitute for turning the Data API off in the
dashboard. Both are intended.
"""

from django.db import migrations

LOCK_DOWN = """
-- 1. Take away every privilege the Data API roles were granted.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;

-- 2. Stop them reaching the schema at all.
REVOKE USAGE ON SCHEMA public FROM anon, authenticated;

-- 3. Make sure tables created by later migrations do not inherit the grants.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;

-- 4. Row-level security with no policies denies everything to non-owner roles,
--    so even a future accidental GRANT does not reopen the data.
ALTER TABLE public.app_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_submission ENABLE ROW LEVEL SECURITY;
"""

# Deliberately partial: this restores schema access and RLS state, but does NOT
# re-grant table privileges. Reversing a security fix should not silently hand
# back DELETE and TRUNCATE to an anonymous role.
UNLOCK = """
ALTER TABLE public.app_submission DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_profile DISABLE ROW LEVEL SECURITY;
GRANT USAGE ON SCHEMA public TO anon, authenticated;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("submissions", "0001_initial"),
        ("accounts", "0001_initial"),
    ]

    operations = [migrations.RunSQL(LOCK_DOWN, reverse_sql=UNLOCK)]
