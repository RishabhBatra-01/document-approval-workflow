# Decision log

Status key: **[OWNER-FIXED]** = fixed by the build brief. **[PROPOSED]** = Claude's recommendation, awaiting owner approval. **[OPEN]** = needs an owner decision.

No entry below records owner approval, because none has been given yet. Human verification is pending for every item in this file.

Created during Phase 0 on 2026-10-24. Nothing in this file has been implemented.

---

## Sources inspected

| Source | Status |
| --- | --- |
| `CLAUDE_BUILD_BRIEF.md` | Read in full (265 lines). |
| `TH-Take-home Challenge_ Document Approval Workflow-290926-092733.pdf` | Read in full. Not in the repo; found at `~/Downloads/`. Text extracted by decoding the PDF's embedded ToUnicode maps (no `poppler`/`pypdf` on this machine). 3 content pages. |
| `Document submissions review dashboard.png` | Viewed. |
| `Travel policy approval workspace.png` | Viewed. |
| Repository | Inspected: no `.git`, no source, no prior project instructions. Only the brief and the two PNGs. |

---

## D1 — Zero mocks everywhere, against an assessment that permits mocking

- **Decision:** No mocks, stubs, fake clients, response interception, or auth bypass in the application or the tests. **[OWNER-FIXED]**
- **Alternative:** The assessment PDF explicitly allows it: *"You're free to mock parts of the system (like data or file storage) to stay within this limit"*, with a 2-hour budget.
- **Reason:** Owner's standard; produces evidence that the real integration path works.
- **Trade-off:** Much larger than a 2-hour build. Tests become slower and dependent on provider availability. Must be disclosed as an extended build, not a 2-hour one.
- **Verification:** Phase 4 runs the suite and reports real timings; README discloses actual effort.
- **Limitation:** Zero mocks does not make all testing better — it makes failure-path testing harder. See D2.

## D2 — How failure paths get exercised without fabricating exceptions

- **Decision:** Induce *real* failures in the isolated test environment instead of monkeypatching returns. **[PROPOSED]**
  - *Auth outage* → point the auth adapter's base URL at a closed local port. The real SDK raises a real connection error; verifies 503-vs-401 mapping.
  - *Storage failure* → target a non-existent bucket / a credential with no grant on it. Real API error from the real Storage service.
  - *Database failure after a successful upload* → inside the real request, violate a real DB `CHECK`/`NOT NULL` constraint (or set a deliberately tiny `statement_timeout`) so the insert genuinely fails after the object is genuinely uploaded. Exercises the cleanup path for real.
  - *Cleanup failure* → delete the uploaded object out-of-band before cleanup runs, so the cleanup delete genuinely fails.
- **Alternative:** Record all four as "unverified, manual plan only", which the brief permits.
- **Reason:** Converts four otherwise-unverifiable rows into genuinely verified ones with no mock, no patched return, and no fabricated exception.
- **Trade-off:** These tests are coupled to real error shapes, so a provider error-message change can break them. They assert on mapped status codes and error `code`s, not on provider strings, to limit that.
- **Verification:** Pending — Phase 2.
- **Limitation:** This is error-*mapping* coverage, not proof the system survives a real multi-minute provider outage.

## D3 — Where the no-mock integration suite runs

- **Decision (brief):** Provision a dedicated **hosted** Supabase test project, separate from the evaluator-facing deployment project. **[OWNER-FIXED]**
- **Verified constraint:** The Supabase Free plan allows **two active projects**, counted across every organization where the account is Owner or Administrator — not two per organization. Free projects are **paused after 7 days of low activity**.
- **Consequence:** deployment project + test project = exactly 2, with no headroom, and local development must share one of them. A test project that pauses mid-week fails the suite for an infrastructure reason.
- **Alternative [PROPOSED]:** Run the suite against the **local Supabase stack via the official `supabase` CLI** (Docker; already installed on this machine). That stack is the real GoTrue, real Storage API and real PostgreSQL — not a fake client, not canned responses, not an in-memory substitute — so it satisfies the no-mocks rule on its substance. Keep the hosted test project for one pre-submission verification pass.
- **Reason to prefer it:** removes the 2-project ceiling, the 7-day pause risk, and cross-run shared-state races from the routine test loop.
- **Trade-off:** The local stack can lag the hosted platform's version, so the hosted pass is still required before submission.
- **Status:** **[RESOLVED 2026-10-24 — owner declined the local stack and chose hosted Supabase directly.]** The proposal was made with its reasons and was not adopted; recorded here so the trade-off is visible rather than lost.
- **Consequences now accepted:** the test suite does real network I/O per test and will be slower; the suite depends on provider availability and on the test project not being paused; the two-project ceiling applies, so the account must have room for a deployment project and a test project.
- **Required mitigations, now mandatory rather than optional:** a configuration guard that refuses to run destructive setup or cleanup unless the configured project ref matches the explicitly declared test project, and that rejects the deployment project ref outright; run-scoped prefixes for every account, object key and record so a run removes only what it created.

## D4 — Token verification via `get_user(jwt)`

- **Decision:** React holds the Supabase session via the official JS SDK and sends the access token to Django as a Bearer token. Django verifies it with `supabase.auth.get_user(jwt)` behind a small auth adapter. Never an unverified JWT decode, never a browser-supplied user id, never a role from user-editable metadata. **[OWNER-FIXED]**
- **Verified:** the documented Python signature is `supabase.auth.get_user(jwt)`, `jwt` optional; it validates the token server-side rather than reading a local session.
- **Trade-off:** one network round trip to Supabase Auth per authenticated request. On Render's free tier (15-minute spin-down, ~1 minute cold start) this adds latency, and Auth rate limits apply.
- **Alternative:** local asymmetric verification against the project's JWKS — also verified, not an unverified decode — documented as the upgrade path behind the same adapter.
- **Decision on caching:** **no** token cache in this version. A short-TTL cache would trade revocation lag for latency; not worth it at three accounts. **[PROPOSED]**
- **Implementation note:** never mutate a shared server client's session with a user's token; verification is a pure call with the token passed in.
- **Verification:** Pending — Phase 1.

## D5 — Disable the Supabase Data API

- **Decision:** Django owns all authorization; React never writes submission records through Supabase's Data API. Disable the Data API for the project. **[OWNER-FIXED]**
- **Verified:** this is supported — Dashboard → Data API integration overview → turn **Enable Data API** off. With it disabled, *"none of the auto-generated REST endpoints respond, regardless of grants or RLS."*
- **Not yet verified:** the Supabase docs do not state how disabling the Data API affects other products. Auth and Storage use their own endpoints rather than PostgREST, so they are expected to keep working, but this must be confirmed empirically.
- **Verification:** Phase 1 smoke test — disable it, then confirm login and an upload still succeed, and confirm a direct Data API call is refused. If disabling breaks a real dependency, flag it and propose equivalent restricted exposure before proceeding.

## D6 — Dependency pins

All versions below were checked against the registries on 2026-10-24.

**Backend** (Python 3.14.7 is what is installed locally):

| Package | Pin | Why | Verified |
| --- | --- | --- | --- |
| Django | 5.2.18 | LTS. Python 3.14 support landed in 5.2.8, so 5.2.x is the LTS that runs on the installed interpreter. | Django's install FAQ: 5.2 supports 3.10–3.14. |
| djangorestframework | 3.18.3 | Serialization, validation, consistent error shapes. | Requires `django>=5.2`; classifiers list Django 5.2/6.0/6.1 and Python 3.14. |
| psycopg[binary] | 3.3.6 | PostgreSQL driver for the Django ORM. | Current release; `requires_python >=3.10`. |
| supabase | 2.33.0 | Official Python SDK — `auth.get_user` and Storage. | Current release. |
| pypdf | 6.21.2 | Server-side PDF structure check and encrypted-PDF detection. Extension and browser MIME are not sufficient. | Current release. |
| django-cors-headers | 4.9.0 | Precise allowed frontend origins for the Bearer architecture. | Current release. |
| gunicorn | 26.2.0 | Production server on Render. Not `runserver`. | Current release. |

Deliberately **not** added: `dj-database-url` (discrete DB env vars instead, so no password-bearing URL is ever constructed, logged, or committed) and `pytest`/`pytest-django` (Django's built-in test runner needs no extra dependency). **[PROPOSED]**

**Frontend** (Node 24.13.0 installed):

| Package | Pin | Why |
| --- | --- | --- |
| react / react-dom | 19.3.1 | Required by the assessment. |
| vite | 7.3.7 | Build tool. **Not** Vite 8 — see note. |
| @vitejs/plugin-react | 5.2.0 | Peer range `^4.2 \|\| ^5 \|\| ^6 \|\| ^7`, so it is the plugin that matches Vite 7. |
| typescript | 5.9.3 | **Not** TypeScript 7.0.2 — see note. |
| react-router | 7.18.4 | Ordinary client-side routing. **Not** v8 — see note. |
| @supabase/supabase-js | 2.118.0 | Official SDK for session management. |
| vitest | 4.1.12 | Frontend behaviour tests. Peer range includes Vite 7. |
| @playwright/test | 1.64.1 | One happy-path browser test. |

- **Note on rejecting the newest majors:** latest today are Vite 8.3.5, TypeScript 7.0.2 and react-router 8.5.0. The brief says to pin compatible stable dependencies and not to blindly use the newest releases. TypeScript 7 is the native-port major and react-router 8 is new enough that ecosystem typings and docs lag; `@vitejs/plugin-react@6` requires `vite ^8.0.0`, so Vite 8 drags the chain with it. The Vite 7 / plugin-react 5 / Vitest 4 / TS 5.9 set is mutually compatible by published peer ranges. **[PROPOSED]**
- **Lockfiles** (`package-lock.json`, and a pinned backend requirements file) are committed. **[OWNER-FIXED]**

## D7 — Status counts without a counts endpoint

- **Decision:** return status counts alongside the list response, computed from the caller's **unfiltered** authorized queryset, not from the filtered page. No separate counts endpoint. **[PROPOSED]**
- **Reason:** the brief warns specifically against deriving all-status counts from an already filtered subset; computing both from one authorized base queryset makes that bug hard to write.
- **Trade-off:** the list response does slightly more work than a bare list.
- **Verification:** Pending — Phase 2 test asserts counts are unchanged by `?status=`.

## D8 — No pagination

- **Decision:** no pagination infrastructure. **[OWNER-FIXED, documented trade-off]**
- **Reason:** three accounts and a handful of synthetic documents.
- **Trade-off:** the list endpoint is unbounded; it would need pagination before any real use. Recorded in the README as production work.

## D9 — Activity history derived, not event-sourced

- **Decision:** derive the two-event activity display from `created_at`/`reviewed_at` and the related actors. No event-log table or framework. **[OWNER-FIXED]**
- **Limitation:** this is a display convenience. It is **not** tamper-proof auditing and will not be described as such.

## D10 — Mockups are visual reference only

- **Decision:** the written requirements win wherever the mockups disagree. The PNGs supply palette, type pairing and layout rhythm only. **[OWNER-FIXED by §5]**
- **See:** the conflict table in the Phase 0 report. The mockups depict at least eleven behaviours the brief excludes (changes-requested status, resubmission, document versions, reviewer assignment, approval chains, due dates, a custom PDF toolbar, non-PDF file types, search, and filler navigation), plus one account holding both roles.
- **Risk if ignored:** building from the images would silently reintroduce excluded scope.

## D11 — Public signup considered and declined

- **Decision:** no create-account page and no password-recovery UI. Login is real; membership is closed. Accounts are created by a provisioning command that takes credentials from the environment or an interactive prompt. **[OWNER-REAFFIRMED 2026-10-24 — owner asked what signup would add, was shown the cost, and chose to stick to the plan]**
- **Alternatives considered:** (a) self-serve signup always creating a submitter, email confirmation off, no reset UI — roughly a day, no new external services, but leaves a locked-out user with no recovery; (b) full signup with confirmation email, password reset and bot protection — requires an SMTP provider and a CAPTCHA provider, both excluded by the brief.
- **Reason:** the assessment does not ask for registration. Self-serve signup forces a role-assignment question whose every browser-influenced answer is a security hole, and the reviewer role is the most load-bearing authorization decision in this build. Closed membership keeps it clean.
- **Trade-off:** the evaluator cannot create their own account and must use the three provisioned ones from the README.
- **Verification:** Phase 2 test asserts an authenticated user with no provisioned profile is denied rather than silently created.

## D13 — Service-role secret key exposed in conversation; rotation declined

- **What happened:** on 2026-10-24 the project's `sb_secret_...` key was pasted into the chat transcript. The publishable key was pasted too, which is harmless — it is public by design.
- **Recommendation:** rotate the secret key (Project Settings → API Keys → revoke). **Declined by the owner, 2026-10-24.** Recorded, not re-argued.
- **Risk accepted:** that key grants full administrative access — it reads and writes every table, bypasses row-level security, and can read or delete every object in the private bucket. Its security now depends entirely on the transcript never being shared.
- **Specific exposure to watch:** this project ships a README documenting AI use and a recorded walkthrough. If any part of this conversation is pasted into the README, attached to the submission, or visible on screen during the recording, the key goes with it.
- **Claude's handling:** the value was never written to disk, never committed, and is not used anywhere. No `.env` file existed and git was not initialized at the time, so there was no secondary leak.
- **Mitigation still in place:** `.gitignore` excludes every `.env`; Phase 4 greps the production frontend build to confirm no secret key is present in shipped JavaScript.

## D12 — Repository is not yet a git repository

- **Observed:** no `.git` in the project directory.
- **Decision:** `git init` and the first commit happen as the first action of Phase 1, not during Phase 0. **[PROPOSED]**
- **Reason:** Phase 0 is planning; the brief forbids fabricating a retrospective history. Nothing will be pushed, and the repository will not be made public or shared, without explicit owner authorization.

---

## AI use and verification (running record)

- **Phase 0:** Claude read the brief, extracted and read the assessment PDF, viewed both mockups, inspected the empty repository, checked local tool versions, and verified the external platform facts cited above against official documentation and package registries. Claude produced this log and the Phase 0 plan.
- **Changed after review:** nothing yet — the owner has not reviewed Phase 0.
- **Checks actually run in Phase 0:** `ls`/`git status` on the project, `node -v` (24.13.0), `python3 -V` (3.14.7), `psql -V` (16.14), `docker`/`supabase` CLI presence, PDF text extraction, PyPI and npm version/peer-range queries, and documentation fetches for Supabase billing, Supabase Data API security, Supabase free-project pausing, Supabase Python `get_user`, and Render free-tier limits.
- **Not run in Phase 0:** no application code, no migrations, no test suite, no provider account changes, no deployment. The hosted Supabase and Render accounts have not been inspected — their real state is assumed from documentation only.
- **Human verification:** pending.

### Configuration verified on 2026-10-24 (real calls, not assumptions)

- **Database:** connected via the session pooler at `aws-0-ap-northeast-2.pooler.supabase.com:5432` with `sslmode=require`. Server reports **PostgreSQL 17.11**; `current_user` and `current_database` are both `postgres`. Session pooler confirmed working, so Django migrations have a supported connection.
- **Storage:** bucket `submissions` exists and `public=False`. No `file_size_limit` and no `allowed_mime_types` are set on the bucket.
- **Auth:** `disable_signup=False` — **public signup is still open at the provider**, contrary to D11. Must be turned off in the dashboard; it is not settable with the service key. `mailer_autoconfirm=False`, so provisioning must create users with email confirmation forced server-side.
- **Env files:** `backend/.env` and `frontend/.env.local` written, `chmod 600`, both covered by `.gitignore`.
- **Password form:** the project's database password contains `@`, which makes the single-URL `postgresql://` form parse incorrectly. The discrete `DB_*` variables chosen in D6 avoid this; a `DATABASE_URL` would have needed percent-encoding.

### Flagged for the deployment gate

- **Region mismatch.** The Supabase project is in `ap-northeast-2` (Seoul). Render's free regions do not include Seoul, with Singapore the nearest. Every authenticated request already costs one `get_user` round trip plus database queries, so cross-region latency compounds. Either accept it and document it, or place the deployment project in a region near the chosen Render region. **[OPEN]**
- **Bucket hardening available.** Setting `file_size_limit` to 5 MiB and `allowed_mime_types` to `application/pdf` on the bucket would add provider-side defence behind Django's own validation. **[PROPOSED]** — not applied; the owner's project is not modified without authorization.

---

## Phase 1 record (2026-10-24)

### D14 — `--keepdb` is required on pooled managed PostgreSQL

- **Observed:** Django creates `test_postgres` successfully, but teardown fails with *"database is being accessed by other users"* because the Supabase session pooler keeps a connection open.
- **Decision:** run the suite with `--keepdb`. The test database is created once and reused. **[PROPOSED]**
- **Alternative:** terminate backends before dropping, which is fragile against a pooler, or a local database, which the owner declined (D3).
- **Trade-off:** the test database persists between runs, so a future schema change must be migrated into it rather than appearing on a fresh create. Runs are faster as a result.
- **Verification:** `./scripts/test.sh` exits 0 with 36 backend tests.

### D15 — The secret-leak check matches values, not prefixes

- **Observed:** grepping `dist/` for `sb_secret` matched, which looked like a leak. It was `supabase-js`'s own key-detection code containing the literal `"sb_secret_"`.
- **Decision:** the check greps for the configured values themselves (`SUPABASE_SECRET_KEY`, `DB_PASSWORD`, `DJANGO_SECRET_KEY`, `DB_HOST`). **[PROPOSED]**
- **Verification:** the real secret value is confirmed absent from the built bundle; the publishable key is present, which is correct.

### D16 — Defect found by the browser pass, not by the tests

- **Observed:** the submissions list crashed to a blank page. `Intl.DateTimeFormat` rejects `dateStyle`/`timeStyle` combined with `timeZoneName`.
- **Fixed** by spelling out the date components, and covered by a regression test (`frontend/tests/dates.test.ts`).
- **Why it matters:** every backend test passed while the page was unrenderable. Recorded as evidence that API tests are not a substitute for running the interface.

### Phase 1 verification status

- **Verified by running:** real login for both roles, role-specific landing routes, upload of a real PDF into the private bucket, pending queue, reviewer approval, submitter seeing the outcome and feedback, logout returning to the login page.
- **Not yet verified:** deployment to Render (not attempted — needs owner authorization), rejection flow end to end in the browser (covered by API tests only), concurrent-decision race under real parallel requests (Phase 2), Data API still enabled (D5 smoke test outstanding), public signup still enabled at the provider.
- **Not a git repository yet** — owner deferred version control.

---

## Phase 2 record (2026-10-24)

### D17 — CRITICAL: Supabase default grants exposed every application table

- **Found:** the Data API was serving `app_submission` to anyone holding the publishable key — the key compiled into the browser bundle. Measured grants: `anon` and `authenticated` each held SELECT, INSERT, UPDATE, DELETE, TRUNCATE and REFERENCES on `app_profile` and `app_submission`, with row-level security disabled on both.
- **Why it happened:** Supabase grants those roles full privileges on new tables in the `public` schema by default. Django migrations create tables there. Nothing in the application code was wrong; the exposure came from the platform default meeting the ORM's default schema.
- **Impact had it shipped:** any visitor could read every submission, delete or truncate all of them, insert fabricated approved records, and — worst — `UPDATE app_profile SET role='reviewer'`, defeating every authorization check in the product. The Django permission layer was never involved, because the Data API bypasses it entirely.
- **Fix:** migration `submissions/0002_lock_down_data_api.py` revokes all privileges on tables, sequences and functions in `public` from `anon` and `authenticated`, revokes `USAGE` on the schema, alters default privileges so later migrations do not re-inherit the grants, and enables row-level security with no policies on both tables. Django connects as the table owner, which is exempt from RLS, so the application is unaffected.
- **Verified:** grants on `public` for those roles now number 0; RLS is on for both tables; a real `GET /rest/v1/app_submission` with the publishable key returns `42501 permission denied`; `/api/health/` and the full workflow still pass.
- **Reverse migration is deliberately partial:** it restores schema usage and RLS state but does not re-grant table privileges. Undoing a security fix should not hand DELETE and TRUNCATE back to an anonymous role.
- **Still outstanding:** turning the Data API off in the dashboard (D5). This migration makes the data safe either way; the two are complementary, not alternatives.
- **Lesson recorded:** the brief's instruction to disable the Data API was not paranoia. Had we relied on "React simply does not call it", the data would have been wide open.

### D18 — Storage deletes fail silently, so cleanup must check the result

- **Found:** `storage.remove()` returns HTTP 200 with an empty list whether the object was deleted, the object did not exist, or the bucket itself does not exist. It never raises. Measured against the real API.
- **Consequence before the fix:** `create_submission`'s compensating cleanup treated "did not throw" as success, so a cleanup that deleted nothing looked identical to one that worked, and the orphaned-object warning could never fire. The `except StorageUnavailable` branch was effectively dead code.
- **Fix:** `remove()` now inspects the response and raises when nothing was deleted.
- **How it was caught:** a real failure-injection test. A mocked client raising an exception would have passed the old test and hidden the defect permanently. This is the clearest evidence so far for the no-mocks rule.
- **Verified:** three tests — delete from a missing bucket raises, delete of a non-existent object raises, delete of a real object succeeds and a second delete of the same key raises.

### D19 — Failure paths are induced, not simulated

Implementing D2. No patched returns, no fabricated exceptions:

| Scenario | How it is really induced | Verified |
| --- | --- | --- |
| Auth outage | Real client pointed at a closed local port; real socket failure | 503, not 401 |
| Invalid token | Real token string against the real reachable service | 401 |
| Storage failure | Real client pointed at a bucket that does not exist | 503, no database row written |
| Database failure after upload | A 400-character title against a real `varchar(150)` column, after a real upload | `DatabaseError`, object cleaned up, no orphan left |
| Cleanup failure | Real upload to the real bucket, deletion aimed at a bucket that does not exist | `ORPHANED STORAGE OBJECT` logged with the key |
| Oversized upload | A real 5 MiB+ body over real HTTP | 413 |

The cleanup-failure case uses a small subclass of the real `SupabaseStorage` whose `remove()` targets a different bucket. It is the real class making real calls to the real service; only the destination differs. No response is faked.

### D20 — Concurrency verified for real

- `TransactionTestCase` with a `threading.Barrier`, so requests genuinely overlap rather than queue. `TestCase` would hide the race, since its uncommitted wrapper transaction makes threads invisible to each other.
- Five simultaneous approvals → exactly one success, four `already_decided`. Two opposing decisions at once → one winner, and the loser overwrites nothing.
- This is the evidence the brief required before claiming race protection is tested.

### Phase 2 verification status

- **Suite:** `./scripts/test.sh` exits 0. 56 backend tests in 196s, 10 frontend tests, typecheck, production build, secret-leak check.
- **Verified in a real browser:** rejection blocked without a reason; rejection with a reason recorded against the right actor; submitter sees the feedback; reviewer Reviewed tab; cross-user isolation visible in the list; the 409 path showing the genuinely saved outcome after a decision made outside the browser.
- **Not yet done:** deployment (needs authorization), the designed interface (Phase 3), Data API disabled in the dashboard, public signup still enabled at the provider, still not a git repository.

---

## Phase 3 record (2026-10-24)

### D21 — The mockups supply a palette, not a product

- **Taken from the images:** forest sidebar `#173E32`, warm ivory canvas `#F7F7F3`, white surfaces, 8/16/24/32 rhythm, 8px corners, a serif reserved for major page titles, sidebar identity and sign-out at the foot.
- **Deliberately not taken:** document versions, "Changes requested", "Revise & resubmit", reviewer assignment, approval routes, due dates, a custom PDF toolbar, non-PDF file types, document search, filler navigation (Policies / Reports / Settings), and the mockup's single account holding both roles.
- **Reason:** §5 of the brief says the written requirements win where the images disagree. Building what the images show would have quietly reintroduced the excluded product.

### D22 — Type and icons are local, not fetched

- A system sans for everything and a local serif stack for page titles. No webfont request, so no layout shift on load and no third-party dependency.
- One inline outline icon family on a 24px grid at 1.6 stroke, inheriting `currentColor`. Icons are `aria-hidden` and `focusable="false"` because each sits beside a text label; status is never conveyed by icon or colour alone.

### D23 — Contrast is computed, not eyeballed

Seventeen foreground/background pairs checked against WCAG AA with a script. All pass; the tightest are `--ink-faint` on canvas at 4.94:1 and the focus ring at 4.81:1 against a 3:1 requirement.

**This is a contrast calculation, not an accessibility audit.** Keyboard reachability, focus order and the Escape/focus-return behaviour were exercised by hand. Screen-reader output, zoom to 200%, and Windows High Contrast were **not** tested.

### D24 — Three layout defects found by looking at the running interface

1. **Table clipped.** `.layout-split` reserved its 380px panel column even with no panel open, squeezing the table. The split class is now applied only when a panel is shown.
2. **Breakpoint too low.** At 1024px a sidebar, a three-column table and a 380px panel do not fit; columns were cut off. Details now become a full page below 1080px rather than 900px.
3. **Decision controls below a tall preview.** Stacked, the 72vh preview pushed Approve and Reject off-screen. The preview is 52vh when stacked.

None of these were visible in the test output. All three came from opening the page.

### D25 — Tables become cards on narrow screens

A four-column table at 375px means horizontal scrolling or unreadable cells. Below 760px each row restacks with its column name beside the value, using `data-label`. The markup stays a real `<table>`, so it is still announced as one.

### D26 — Link semantics corrected

The reviewer's Pending/Reviewed tabs are links, and were using `aria-pressed`, which belongs to buttons. They now use `aria-current="page"`; the stylesheet honours both so the filter chips (real buttons) are unaffected.

### Phase 3 verification status

- **Suite:** `./scripts/test.sh` exits 0 — 56 backend tests in 207s, 18 frontend tests, typecheck, production build, secret-leak check.
- **Seen running, desktop (1024px):** login, submitter list, details panel, upload form with file card, reviewer queue, reviewer detail with the browser's native PDF viewer, decision panel.
- **Seen running, narrow (375px):** topbar with menu, drawer with scrim, stacked card rows, no horizontal scroll.
- **Keyboard verified by hand:** Escape closes the details panel and focus returns to the row that opened it; Escape closes the drawer and focus returns to the menu button.
- **Not visually inspected:** tablet widths between 760 and 1080px beyond the breakpoint change itself; print; forced-colours mode; the upload error and in-flight states in the new design (their logic is unchanged from Phase 2 and still covered by tests).

---

## Phase 4 record (2026-10-24)

### D27 — Nested routes would have 404'd on the deployed site

- **Found:** serving the production build from a plain static server (no SPA fallback — which is what Render Static Sites do by default) returns **404** for `/submissions/new`, `/review/done` and `/review/document/<id>`. Only `/` worked.
- **Impact had it shipped:** every page refresh on a detail view, and every link pasted into a browser or an email, would have shown a 404. The evaluator's first deep link would have failed.
- **Cause:** Phase 1 was supposed to prepare the "frontend routing rewrite" and did not. Env examples, the health route and migrations were done; the rewrite was missed. Recorded as an own miss, not a platform surprise.
- **Fix:** `render.yaml` now declares both services, with a rewrite of `/*` → `/index.html` on the static site.
- **Verified:** with the fallback in place all six routes return 200, and real assets still serve as themselves (`/assets/index-*.js` → 200 `text/javascript`), so the rewrite does not swallow files.
- **Honest limitation:** Render's published docs describe this rule **in the dashboard** (Action: Rewrite, Source `/*`, Destination `/index.html`) and do not show the `render.yaml` keys. The blueprint block is written in the documented spec shape but **could not be quoted from the docs**, so it must be confirmed on first deploy; the dashboard route is the verified fallback. A comment in the file says so.

### D28 — The two submitter accounts shared a password

- **Found:** the provisioning command keyed passwords by *role*, so both submitters received the same one from `PROVISION_PASSWORD_SUBMITTER`.
- **Why it matters:** the product's central guarantee is that submitter A cannot read submitter B's documents. Sharing a credential between them makes that guarantee rest on a shared secret, and anyone handed one account's password holds the other's.
- **Fix:** passwords are keyed per account (`PROVISION_PASSWORD_SUBMITTER_A`, `_SUBMITTER_B`, `_REVIEWER`). The existing `submitter-b` password was deliberately rotated so the live accounts are distinct too, not just future ones.
- **Verified:** the two passwords differ; each account signs in with its own; signing in to B with A's password is rejected.

### D29 — Repository hygiene

Removed four empty Django scaffolding files (`admin.py` and `tests.py` in both apps) — the admin is not installed and the real tests live in `backend/tests/`. Removed a committed `tsconfig.tsbuildinfo` and added `*.tsbuildinfo` to `.gitignore`. Confirmed no `.env` file appears in the set of files that would be committed.

### Phase 4 verification results

| Check | Result |
| --- | --- |
| One-command suite | **Pass** — exit 0, 62 backend + 18 frontend |
| Type check, production build, Django checks | **Pass** |
| Real PostgreSQL conflict check | **Pass** — 5 simultaneous approvals, 1 winner |
| Full flow, both roles, two submitters | **Pass** — in the browser |
| Private file access | **Pass** — public path, no-credential and publishable-key fetches all denied; valid signature works |
| Expired and tampered signatures | **Pass** — both denied; TTL genuinely enforced |
| Direct Data API denial | **Pass** — `42501 permission denied` on read, write and delete |
| Frontend secret absence | **Pass** — no secret value in `dist/` |
| Logout isolation | **Pass** — `localStorage` completely empty after sign-out; second account saw none of the first's data |
| Cross-user access with a real token | **Pass** — read 404, file-url 404, decide 403, list returns only own rows |
| Frontend route guard | **Pass** — submitter redirected off the reviewer route, nothing flashed |
| Malformed uploads | **Pass** — empty, non-PDF, truncated, encrypted, oversized all rejected |
| Stale decisions | **Pass** — 409 preserves the first outcome, UI shows the saved one |
| Page refresh on nested routes | **Fixed, then pass** — see D27 |
| Deployed settings | **Could not run** — nothing is deployed |

### What could not be verified, and why

- **Everything about the deployment.** No Render service exists, so `DEBUG=False` behaviour, `ALLOWED_HOSTS`, the real CORS origin pair, HTTPS redirect, the cold-start experience, cross-region latency to Seoul, and the `render.yaml` rewrite block are all **unverified**. They are configured, not proven.
- **The Data API dashboard toggle.** The migration makes the data safe regardless, but the toggle itself is still on and is not settable with the service key.
- **Public signup.** Still enabled at the provider; dashboard-only.
- **Accessibility beyond contrast and keyboard.** No screen-reader testing, no 200% zoom, no forced-colours mode.
- **Version control.** Still not a git repository, at the owner's direction.

---

## D30 — Removed an unused Django component and its table (2026-10-24)

- **Prompted by:** the owner asking why the database had four tables when the product has two.
- **Found:** `django.contrib.contenttypes` was in `INSTALLED_APPS` because it ships in Django's default project template, not because anything needed it. It exists so Django features can refer to "a row in any model" — what the admin's permission system and generic foreign keys use. This project has no admin, no generic relations, and roles in `app_profile` rather than Django permissions. A grep found zero references in our code. Its table held three rows naming our own models, read by nothing.
- **Fix:** removed from `INSTALLED_APPS`; migration `0003` drops the table with `IF EXISTS`, so a fresh database (which never creates it) and an existing one both end up the same.
- **Verified:** `manage.py check` clean, full suite still passes (62 backend, 18 frontend), and the database now holds three tables — `app_profile`, `app_submission`, and Django's `django_migrations` ledger.
- **Why it is worth the change:** the owner has to explain this system. "Two tables of ours plus one migration ledger" is the truth; a fourth table that nothing reads is clutter they would have had to explain away.

---

## D31 — Whole rows are clickable, not just the title (2026-10-24)

- **Prompted by:** the owner noticing that only the document title responded to a click, while the rest of the row — submitter, status, date, whitespace — was inert despite looking like one object.
- **Change:** the whole row opens the document, in both tables (reviewer queue → detail page, submitter list → details panel).
- **What the row click deliberately does NOT do**, via a shared `shouldIgnoreRowClick` helper:
  - fire when the click landed on a link or button inside the row, which would otherwise navigate twice;
  - fire while text is selected, so dragging across a submitter's name to copy it does not also open the document;
  - hijack cmd/ctrl/shift-click or middle-click, which keep their normal browser meaning.
- **Accessibility:** the title stays a real link (reviewer) or button (submitter) underneath, so keyboard users still have a focusable target, and right-click → open in new tab still works on the reviewer queue. A row with only a click handler would be invisible to a keyboard. Focus now outlines the whole row rather than a few characters of text.
- **Verified in the browser:** clicking the submitter-name cell opens the reviewer detail; clicking empty space in a submitter row opens the panel; a programmatic text selection followed by a click does **not** navigate; Escape still closes the panel and returns focus to that row's title button.
- **Also fixed in passing (D21 follow-up):** `defaultCollapsed` was passed to only one of the three `AppShell` renders in `ReviewDetail`. React keeps state from whichever mounted first — the loading branch — so the icon rail never appeared. All three branches now agree.

---

## D32 — In-flight feedback, and a misleading button (2026-10-24)

- **Prompted by:** the owner noting there was no visible motion while an upload or a decision was processing.
- **Found while checking:** pressing **Reject** made the **Approve** button read "Saving…" while Reject still read "Reject". The button that was not pressed announced the work. Nothing broke — both were disabled — but it reported the wrong action. Fixed by tracking *which* decision is in flight (`'approve' | 'reject' | null`) rather than a boolean.
- **Spinner:** indeterminate on purpose. A plain multipart POST reports no measurable progress, and a bar that creeps to 90% and waits is a lie — the brief forbids exactly that. The button's text carries the meaning; the spinner only shows that work continues.
- **Delayed by 250ms** (`useDelayedFlag`): a decision is one database write and often finishes well under a second. A spinner that appears and vanishes reads as a glitch, so fast actions now show nothing at all.
- **Reduced motion:** the spinner is hidden entirely rather than frozen mid-rotation, which looks like a broken image. The text state remains, so no information is lost.
- **Cold-start message (the most valuable part):** after 3 seconds a line appears explaining the server may be waking up and that this can take up to a minute on free hosting. Render's free tier spins down after 15 minutes of no traffic, so an evaluator's first click will often be a cold start; a silent spinner for 45 seconds reads as "broken".
- **Success confirmation:** a successful upload now hands the new submission's id and title to the list, which shows "<title> was submitted for review" and highlights the new row for 8 seconds. Previously the user was returned to a list where a row had silently appeared — the anxious moment is right after submitting, not during.
- **Layout stability:** buttons whose label changes while working now hold their width, so "Submit for review" → "Uploading…" no longer nudges the layout.
- **Bug caught during verification:** the confirmation banner did not render, because the effect clearing the navigation state ran before the banner read the title from it. The title is now copied into component state on first render.
- **Rejected as an approach:** optimistic UI for decisions. With the real 409 conflict path it would flash "Approved" and then flip to "someone else already rejected this" — worse than waiting.
- **Verified in the browser:** a real upload showed the skeleton, then the confirmation banner and highlighted row with counts updated; a real rejection, inspected 300ms in, showed `Approve` disabled with no spinner and `Rejecting…` disabled with a spinner.
- **Not implemented, still available:** genuinely measured upload progress via `XMLHttpRequest`, which can report real bytes sent. Offered and not taken up; `fetch` cannot do this.

---

## D33 — The leaf mark from the supplied design (2026-10-24)

- **Prompted by:** the owner noticing the mockup's top-left logo — a two-leaf sprout — was missing from the build, which used a generic document icon.
- **Taken from the reference** by cropping the mockup and enlarging it (`magick … -crop 110x100+0+0`), rather than guessing from memory: a solid mark, a larger right leaf with a vein, a distinctly smaller left leaf, both meeting at a single base point.
- **Drawn as SVG**, not imported as an image: it stays sharp at any size, adds no network request, and cannot 404.
- **Solid, unlike the rest of the icon set**, which is outlined at 1.6 stroke. A logo is a mark, not an icon; the contrast is deliberate.
- **The vein is cut out, not drawn on top** — one path with `fill-rule="evenodd"`, so whatever is behind shows through. That is why the same component works white on the forest sidebar and forest on the ivory login card without a second copy.
- **Corrected after looking at it enlarged:** the first attempt made both leaves nearly equal, while the reference has a clearly smaller left leaf. Adjusted and re-checked at 240px.
- **Also now the favicon**, inlined as a data URI on a forest rounded square, so the browser tab matches and no icon file can go missing.
- **Verified in the browser:** renders in the sidebar (white on forest), on the login card (forest on white), and enlarged to 240px to confirm the silhouette.

---

## D34 — The "just submitted" highlight never cleared (2026-10-24)

- **Reported by the owner**, from their own screenshot: the newly uploaded row stayed highlighted indefinitely rather than settling.
- **Cause — a self-cancelling effect.** One `useEffect` did two jobs: clear the router's navigation state, and start the timer that removes the highlight. Clearing the state changed `created.createdId`, which is that effect's own dependency. React therefore ran the effect's cleanup — cancelling the timer it had just created — then re-ran the effect, which returned early because the id was now gone. The timer never fired, so the confirmation and the highlight stayed forever.
- **Fix:** two effects. One clears the navigation state; the other owns the timer and is keyed on the confirmation itself, so nothing it does can cancel it.
- **Hardening:** the row highlight is now a CSS animation that fades to transparent over 2.2s, rather than a colour held by component state. The colour settles on its own even if the timing logic were wrong again — a stuck piece of state can no longer leave a row permanently green. Suppressed under `prefers-reduced-motion`, where the confirmation message above the table carries the meaning instead.
- **Verified in the browser** by sampling the row's computed background after a real upload: green at ~3.5s, `rgba(0, 0, 0, 0)` by ~6.5s, and both the banner and the highlight gone shortly after.
- **Worth noting:** this is the second bug in this feature caused by that single effect doing two unrelated things. The first swallowed the confirmation's title; this one swallowed its timer.

---

## D35 — The sign-in page was a card in an empty room (2026-10-24)

- **Reported by the owner:** at desktop width a 420px card floating in the middle of a large ivory page looked unfinished and gave no sense of what was behind the door.
- **Checked first, rather than decorating:** accessibility guidance on login forms (real `<label>` elements rather than placeholders, `autocomplete` on both fields, errors in text and not colour alone). The form already satisfied all of it — the problem was purely compositional, so nothing about the form's behaviour changed.
- **Now a two-panel layout.** Left: the product's own forest green, carrying the wordmark, a serif headline, and the three steps the product actually performs — Submit, Review, Decision. Right: the form on the ivory canvas.
- **Deliberately not added:** testimonials, usage statistics, customer logos, "trusted by" rows. Every one would have to be invented, and the brief forbids filler. The three steps are description, not decoration: each is something the product genuinely does.
- **An oversized leaf watermark** at 4.5% opacity gives the panel texture without competing with the text.
- **Narrow screens drop the brand panel entirely** below 880px and show a compact wordmark above the form instead. On a phone the form is what the user came for; a tall green panel above it is just scrolling.
- **Contrast re-checked** on the new surfaces: headline and wordmark 10.9:1, step detail 6.8:1, footnote 4.9:1 — all pass AA.
- **Verified:** rendered at desktop and 375px, and a real sign-in still works after the rewrite.

### D36 — Sidebar label wrapped once the count reached double digits

Spotted in the same screenshot: "My submissions" broke onto two lines when its count badge read `11`. The label now stays on one line and truncates; the count no longer moves. Only visible once a test account had ten submissions, which is a reminder that layout bugs hide behind small sample data.

---

## D37 — Route transition on the reviewer side (2026-10-24)

- **Requested by the owner:** opening a document from the queue swapped screens as a hard cut.
- **Chosen motion:** fade with an 8px rise, 180ms, ease-out.
- **Rejected — slide from the right:** a mobile stack idiom. With a persistent sidebar it reads as a phone app bolted onto a desktop one, it moves the most pixels (the PDF frame is the largest thing on screen), and it forces a second decision about which way "back" slides.
- **Rejected — plain fade:** reads as "the screen redrew" rather than "something arrived". The small rise is what makes it feel deliberate.
- **The decision that matters most:** only `.main__inner` animates. The sidebar deliberately does not. Fading the whole screen looks like a full page reload, which is the feeling an SPA transition exists to avoid. Verified: the sidebar has no animations running during a route change.
- **No dependency added** — a CSS animation keyed on route mount. An animation library would be significant weight for one transition.
- **Direction-agnostic**, so going back needs no separate rule or reverse logic.

### The subtle part: `backwards`, not `both`

The first version used `animation-fill-mode: both`. That keeps the final keyframe applied after the animation ends, and `transform: none` in a keyframe computes to an identity matrix — which **still makes the element a containing block for `position: fixed` descendants**. The submitter's details panel is `position: fixed; inset: 0` on narrow screens and would have been confined to the content column instead of covering the viewport.

`backwards` applies only the FROM state before the animation starts, so afterwards the element carries no transform at all.

Verified by measurement, not inspection: computed `transform` is `none` after the animation, and a `position: fixed` probe inserted inside the animated container measures 1024×768 — the full viewport — while its parent is 712px wide starting at x=280.

### D38 — Regression caught by an expired session

While testing, the reviewer's token expired and the app showed its "Account unavailable" state — correct behaviour, but visibly mis-laid-out. The login redesign (D35) had replaced `.auth__card` and `.auth__brand`, while `App.tsx` still used them for its two full-page states: loading an identity, and an authenticated-but-unprovisioned account. Both were being laid out as half of a two-column grid.

Given their own `.standalone` classes. Worth noting these states are hard to reach deliberately, so the regression surfaced only by chance — a reminder that rarely-seen screens need explicit checking after a layout change.

---

## D39 — The transition was real but imperceptible (2026-10-24)

- **Reported by the owner:** "I don't see it."
- **Ruled out first:** macOS Reduce Motion was off (`defaults read com.apple.universalaccess reduceMotion` — not set) and the browser reported `prefers-reduced-motion: false`, with `page-enter` applied. So it was running, just not noticeable.
- **Root cause, and the useful lesson:** the animation was keyed to **route mount**, which happens when the *loading skeleton* appears. The real content arrives several hundred milliseconds later, by which time the animation had long finished — so the thing the user actually looks at appeared with no transition at all. Motion was being spent on a placeholder.
- **Fix:** an `.enter` class on the loaded content itself, keyed on the submission id so opening a different document replays it. The route frame still animates; the content now animates when it genuinely arrives.
- **Second cause — the curve.** The first attempt (180ms, 8px, `cubic-bezier(0.22, 1, 0.36, 1)`) measured **55% complete at 46ms**. Technically running, over before the eye registers it. Now 320ms over 18px with `cubic-bezier(0.33, 1, 0.68, 1)`.
- **Measured, not eyeballed** — sampling the computed style during a replay:

| | 47ms | 94ms | 141ms | 188ms | 235ms | 280ms |
| --- | --- | --- | --- | --- | --- | --- |
| opacity | 0.34 | 0.64 | 0.80 | 0.90 | 0.97 | 1 |
| rise (px) | 11.8 | 6.6 | 3.6 | 1.8 | 0.5 | 0 |

- **A measurement error worth recording:** the first attempt to sample this showed the element frozen at the start frame. The cause was a stale DOM reference — React had replaced the node mid-animation, and `getComputedStyle` on a detached element reports the fill state, which looks exactly like a stuck animation. Re-querying the element each sample fixed the reading. The animation was never broken; the instrument was.

### Noticed but not fixed: expired sessions are reported as an account problem

The reviewer's token expired twice during this work. The app handles it correctly — 401, no protected data shown — but the screen is headed **"Account unavailable"** with "Your session is not valid", which reads like a provisioning fault rather than a routine expiry. `invalid_token` (expired — should simply return the user to sign-in) and `profile_not_provisioned` (genuinely blocked) are distinct conditions and the UI treats them the same. Flagged, not changed.

---

## D40 — Latency: measured, then halved (2026-10-24)

Asked whether loading could be made faster. Measured first rather than guessing. All figures are medians from this machine to the Supabase project in `ap-northeast-2` (Seoul).

### What each piece actually costs

| Operation | Median |
| --- | --- |
| `auth.get_user(token)` — on **every** authenticated request | 188 ms |
| Database round trip on an **open** connection | 156 ms |
| Database round trip on a **new** connection | 1110 ms |
| `create_signed_url` — only when opening a PDF | 194 ms |

### Fix 1 — connection reuse (the big one)

`CONN_MAX_AGE = 0` was set in Phase 1, so Django closed its database connection after every request and paid a fresh TCP plus TLS handshake across the Pacific each time: **~954 ms of pure overhead per request**.

Now `CONN_MAX_AGE = 600` with `CONN_HEALTH_CHECKS = True`, so a connection the pooler has dropped is replaced rather than erroring. Each worker holds one pooler slot; two gunicorn workers can afford that.

**This is invisible under `runserver`**, which spawns a thread per request while Django keeps connections per thread — so nothing is reused and the measurement does not move. It only shows under gunicorn, which is what production runs. Worth remembering before concluding a fix "did nothing".

### Fix 2 — the health check was doing the two slowest things in the app

`/api/health/` measured **1301 ms**. DRF runs authentication whenever a token is present, even where the permission class is `AllowAny` — so a liveness probe was verifying a token with Supabase *and* loading a profile from the database. Now `@authentication_classes([])`: **6 ms**.

This matters beyond local timings: Render pings the health path, and a probe that depends on Auth and the database will report the service unhealthy whenever either is slow.

### Fix 3 — one query instead of two for the list

Counts came from a separate aggregate query — a second round trip, ~156 ms. There is no pagination, so every authorized row is fetched anyway; counting and filtering them in Python is free by comparison, and makes the counts structurally unable to disagree with the rows returned. **Only sound while result sets are small — adding pagination means going back to an aggregate query.**

### Result

| Endpoint | Before | After | Change |
| --- | --- | --- | --- |
| `GET /api/health/` | 1301 ms | **6 ms** | −99.5% |
| `GET /api/me/` | 1289 ms | **522 ms** | −59% |
| `GET /api/submissions/` | 1640 ms | **673 ms** | −59% |

Full suite still passes: 62 backend, 18 frontend.

### Available but not done: local JWT verification

The remaining large cost is the 188 ms `get_user()` call on every request. **Verified: this project already issues ES256 tokens and publishes a JWKS** at `/auth/v1/.well-known/jwks.json` with one EC key — so signature verification could happen in-process with no network call, taking the list endpoint to roughly 485 ms.

This is the upgrade D4 anticipated, which is why token verification sits behind an adapter. It is **not** an unverified decode: the signature is checked against the project's published public key.

The honest trade-off is revocation. With `get_user()`, a revoked session stops working immediately. With local verification it remains valid until the token expires, because key caches lag. Note that application role changes take effect immediately either way, since the profile is still read from the database on every request.

Not implemented — the brief fixed `get_user()` as the mechanism, so switching is the owner's decision rather than a tuning change.

### Not investigated

Frontend bundle size (519 kB raw, 150 kB gzipped), the reviewer detail page making its two requests sequentially rather than in parallel, and anything about the deployed environment, which does not exist yet.

---

## D41 — The detail page asked for two things one at a time (2026-10-24)

- **Found:** `ReviewDetail` awaited the submission, then awaited its signed URL. The second request does not depend on the first — the server authorises it from the id either way — so the wait was doubled for nothing.
- **Fix:** both requests issued together with `Promise.allSettled`.
- **`allSettled`, not `all`:** a failed preview link must not take the page down. The document still loads and Open PDF can retry.
- **Measured** against gunicorn with 2 workers, as `render.yaml` specifies:

| | Median |
| --- | --- |
| one after the other | 1980 ms |
| both at once | **941 ms** |

- **A measurement trap worth recording:** with **1** gunicorn worker the same change showed only 1693 → 1536 ms, because the two "parallel" requests simply queued behind each other on the server. Client-side parallelism is worth nothing if the server handles one request at a time. The improvement is real only because production runs two workers.
- **Confirmed in the browser**, not just the benchmark: 920 ms from clicking a queue row to the document being usable.

## D42 — An expired session was reported as a broken account

- **Surfaced by accident, three times**, while doing other work: a lapsed token showed a screen headed **"Account unavailable"** saying "Your session is not valid". Technically true, badly wrong in meaning — it reads as *your account has a problem* when the user has simply been away for an hour.
- **Cause:** the session layer treated every `ApiError` from `/api/me/` as "blocked". A 401 (expired or invalid token) and a 403 (`profile_not_provisioned`) are different conditions and were handled identically.
- **Fix:** a 401 now signs out and returns to the sign-in page. "Blocked" is reserved for an authenticated user with no application profile, which genuinely must not reach a protected screen.
- **Verified in the browser:** an expired reviewer session now lands on the sign-in page instead of the error card.
- **Worth noting it would have appeared in the walkthrough.** Tokens last about an hour; a recording session easily runs longer. No automated test covers this path — it is browser-verified only.

### Running totals after all latency work

| Endpoint | Before | After |
| --- | --- | --- |
| `GET /api/health/` | 1301 ms | 6 ms |
| `GET /api/me/` | 1289 ms | 522 ms |
| `GET /api/submissions/` | 1640 ms | 673 ms |
| Reviewer detail (click → usable) | 1980 ms | 941 ms |

Still available and not done: local JWKS verification (−188 ms on every authenticated request; owner's decision, see D40) and the 519 kB frontend bundle.

---

## D43 — Accepted file types widened to PDF and images (2026-10-24)

- **Owner decision**, changing the brief's fixed "one PDF per submission".
- **The rule applied:** a file is accepted only if a reviewer can read it **in the browser**. Browsers ship a PDF engine and an image decoder and nothing else, so those are the formats that keep the review loop intact. Accepting a Word file would mean the reviewer downloads it, opens another program, and comes back to decide — which stops being a review.
- **Accepted:** PDF, PNG, JPEG, WebP. The realistic non-PDF document is a scan or a phone photograph of a signed form.
- **Refused, with advice:** Word, Excel, PowerPoint and legacy Office now say the file cannot be reviewed in the browser and to export it as a PDF. A refusal that tells you what to do next is worth more than one that only says no.
- **Refused outright:** SVG and HTML (a browser executes them — an XSS vector dressed as a document), archives, and anything unrecognised. GIF is refused too: the accepted list is an allowlist, not "whatever the image library can open".
- **The type still comes from the bytes**, never the filename or the browser's claimed content type. A PNG named `report.pdf` is detected as a PNG, stored with a `.png` key and recorded as `image/png`. There is a test for exactly that.

### EXIF is stripped, and why that was not obvious

Photographs routinely carry GPS coordinates, the device, and a timestamp. Someone submitting a phone photo of a signed form is unlikely to realise they are also submitting where they were standing.

This sits awkwardly against the principle stated in D43's own discussion — that the original is the record of what was submitted — because stripping metadata means the stored bytes differ from the upload. Resolved in favour of the submitter's privacy: JPEGs are re-saved with `quality="keep"`, which reuses the original quantization tables rather than re-compressing, so the **visible image is unchanged** and only the metadata segments are removed. A test asserts pixel-for-pixel equality before and after.

### Security note worth keeping

Every accepted format is new parser surface. Images are decoded by Pillow, which has its own CVE history, so the allowlist is deliberately short and each file is decoded before anything else happens to it. This is also the argument against Office conversion: the converter, not the conversion, is the risk.

### Verified

- 17 new unit tests plus 3 integration tests; full backend suite 75 tests, all passing.
- End to end in the browser: a scanned expense-claim PNG submitted, listed, opened by the reviewer, and rendered inline with "Open image" rather than "Open PDF".

### Documented as production work, not built

Word and PowerPoint via **server-side conversion to PDF** — LibreOffice headless, run in a sandbox with memory limits and a timeout, triggered by a background job or lazily on first view with the result cached. The original stays the record of what was submitted; the PDF is a derived preview artifact.

Excel is the exception: converting a spreadsheet to pages loses the formulas behind the numbers and slices wide sheets arbitrarily. Spreadsheets need a grid viewer, not a different converter.
