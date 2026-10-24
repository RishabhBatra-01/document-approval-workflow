# Document Review

A small approval tool. Someone uploads a document, a reviewer reads it and approves or rejects it, and the person who sent it sees the outcome and the feedback.

Two roles, three states, one legal transition. That is the whole product, and keeping it that small was deliberate.

- **Backend:** Django 5.2 with Django REST Framework
- **Frontend:** React 19, TypeScript, Vite
- **Database, auth and file storage:** Supabase (PostgreSQL, Supabase Auth, private Storage bucket)

### Links

| | |
| --- | --- |
| **Video walkthrough** | _not recorded yet_ |
| **Hosted demo** | _not deployed yet. `render.yaml` is written and untested._ |

### Demo accounts

| Email | Role | Password |
| --- | --- | --- |
| `submitter-a@example.com` | Submitter | `Dr5LnpiyHxssyoMU5hMW!7` |
| `submitter-b@example.com` | Submitter | `DruAgl1GuqvHrnQQeg1f!7` |
| `reviewer@example.com` | Reviewer | `DrdZv7ib0DKT4xaWnMAb!7` |

Two submitters rather than one, because the most interesting thing to try is that submitter A genuinely cannot see submitter B's documents, and that needs two accounts.

These are throwaway accounts on a demo project, in a private repository, which is the only reason passwords appear in a file at all. In anything real they would not be here, and the provisioning command exists so that you never have to put them in one: it prompts for each password and writes none of them to disk.

---

## Contents

1. [What it does](#what-it-does)
2. [Setup](#setup)
3. [Running the tests](#running-the-tests)
4. [Architecture](#architecture)
5. [Data model](#data-model)
6. [State transitions](#state-transitions)
7. [API design](#api-design)
8. [Major decisions and trade-offs](#major-decisions-and-trade-offs)
9. [Security notes](#security-notes)
10. [Performance](#performance)
11. [AI tools used](#ai-tools-used)
12. [What I would add for production](#what-i-would-add-for-production)
13. [Known limitations](#known-limitations)
14. [Effort](#effort)

---

## What it does

**A submitter** signs in, uploads a document with a title and optional context, and watches its status. They can filter by status and read the reviewer's feedback once a decision is made.

**A reviewer** signs in to a queue of pending documents, oldest first. They open one, read it in the browser, and approve or reject it. Rejecting requires a reason.

Roles are exclusive. A submitter never sees the review queue, and a reviewer cannot upload. There is no sign-up page: accounts are created by an administrator, which is covered under [Major decisions](#major-decisions-and-trade-offs).

Accepted files are PDF, PNG, JPEG and WebP, up to 5 MiB. The reasoning for that specific list is in [Major decisions](#major-decisions-and-trade-offs) too.

---

## Setup

You need two terminals: one for the API, one for the web app.

### Prerequisites

- **Python 3.12 or newer.** Built and tested on 3.14.
- **Node 20.19 or newer.** Built and tested on 24.13. Vite 7 will refuse older versions.
- **A Supabase project.** Free tier is fine. You need the project URL, the publishable key, the secret key, and the database connection details.

### Supabase, once

1. Create a project and note which region you pick, since it appears in the database host.
2. Under **Storage**, create a bucket called `submissions` and leave the public toggle **off**. A public bucket would hand out every document by URL and defeat the permission model.
3. Under **Authentication → Sign In / Providers**, turn off **Allow new users to sign up**. There is no sign-up page in the app, and this closes the same door at the provider.
4. Under **Project Settings → Database → Connection string**, use the **Session pooler** values. Do not use the transaction pooler on port 6543: it does not support prepared statements and Django migrations will fail against it in confusing ways.

### Backend

```bash
cd backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

cp .env.example .env
# then fill in .env, see the comments in the file
```

Generate a Django secret key rather than inventing one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Apply the schema and create the accounts:

```bash
set -a && source .env && set +a
./.venv/bin/python manage.py migrate
./.venv/bin/python manage.py provision_accounts
```

`provision_accounts` prompts for each password. It never takes them as command line arguments, which would put them in your shell history, and it never writes them to a file. Running it again leaves existing accounts alone rather than silently resetting passwords.

It creates three accounts:

| Email | Role | Name |
| --- | --- | --- |
| `submitter-a@example.com` | submitter | Alex Morgan |
| `submitter-b@example.com` | submitter | Priya Shah |
| `reviewer@example.com` | reviewer | Sam Patel |

You choose the passwords when the command prompts. The ones listed under [Demo accounts](#demo-accounts) are for the hosted demo; a local setup uses whatever you type here.

Start the API:

```bash
./.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 2
```

`manage.py runserver` also works for development, but it is noticeably slower. The reason is explained under [Performance](#performance), and it is worth reading before you conclude the app is slow.

### Frontend

```bash
cd frontend
npm install

cp .env.example .env.local
# fill in the project URL and publishable key

npm run dev
```

Open **http://localhost:5173**.

### A note on the two environment files

`backend/.env` holds everything secret: the secret key, the database password, the Django key. `frontend/.env.local` holds only the project URL and the publishable key, both of which are compiled into the JavaScript bundle and visible to anyone who opens the site.

That split is the point. The test suite greps the production build for the backend values to confirm none of them leak, and that check runs every time.

---

## Running the tests

One command:

```bash
./scripts/test.sh
```

It runs Django system checks, 75 backend tests, a TypeScript type check, 18 frontend tests, a production build, and a scan of the built bundle for leaked secrets. It exits non-zero if any stage fails, so it works in CI unchanged.

Takes about three and a half minutes.

### These tests use real services

Nothing is mocked. No fake clients, no intercepted HTTP, no in-memory substitutes. Every token comes from a real sign-in, every upload lands in your real bucket, and the concurrency tests run against real PostgreSQL.

That has consequences you should know before running it:

- **It needs network access and a configured `backend/.env`.** Without them it fails with a clear message rather than skipping.
- **It refuses to run against the wrong project.** If `SUPABASE_URL` does not match `SUPABASE_TEST_PROJECT_REF`, it stops before touching anything. These tests create and delete real accounts and real files, so pointing them at a project with real data would be destructive.
- **It is slower than a mocked suite**, and it depends on Supabase being up.

I chose this because mocks test that a fake behaved as programmed. Twice during this build, that difference caught a real bug that a mock would have hidden. Both are described under [Major decisions](#major-decisions-and-trade-offs).

---

## Architecture

```
Browser                          Django API                  Supabase
───────                          ──────────                  ────────
React + TypeScript
  │
  ├── supabase-js ──────────────────────────────────────────▶ Auth
  │     (session only)                                        (sign in,
  │                                                            issue token)
  │
  └── Bearer token ──────────▶ verify token ─────────────────▶ Auth
                                     │
                                     ├── look up Profile ────▶ PostgreSQL
                                     │   (role lives here)      (Django ORM)
                                     │
                                     ├── scoped queries ─────▶ PostgreSQL
                                     │
                                     └── signed read URL ────▶ Storage
                                         (5 minute expiry)      (private bucket)
```

**The browser is trusted to prove who you are, and nothing else.** It holds a Supabase session, and that is all. Every authorization fact (who you are, what role you have, which rows you may see) is re-derived on the server from the verified token on every single request.

Three consequences worth stating, because they are the decisions that matter:

**The role is not in the token.** Supabase lets users edit their own metadata, so a role stored there would be self-assignable. The role lives in a Django-owned table that no browser can write to. The JWT's own `authenticated` role is not this application's reviewer role.

**React never writes application data through Supabase.** All writes go through Django, which re-checks permission. The auto-generated Data API is actively locked out, which is covered under [Security notes](#security-notes) and is the most important thing in this README.

**Files are never public.** The bucket is private, the browser holds no key that can read it, and a signed URL is issued only after Django has confirmed the caller is allowed. Those URLs expire after five minutes and are never stored or logged.

### Project layout

```
backend/
  config/            settings, URLs, the shared JSON error shape
  accounts/          Profile model, token authentication, provisioning command
  submissions/       model, validation, serializers, permissions, the decision operation
  integrations/      the only two files that talk to Supabase Auth and Storage
  tests/             75 tests, all against real services
frontend/
  src/lib/           API client, session handling, Supabase client
  src/routes/        login, submitter list, upload form, reviewer queue, reviewer detail
  src/components/    app shell, icons, shared pieces
scripts/test.sh      the single test command
docs/decision-log.md every decision, measurement and bug, written as it happened
render.yaml          deployment blueprint
```

`integrations/` exists so that there are exactly two files to read if you want to know how this talks to Supabase. Everything else is ordinary Django.

---

## Data model

Two tables. That is not an accident of scope, it is the design.

### `app_profile`

Who someone is, and what they are allowed to do.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID | primary key |
| `auth_user_id` | UUID | the verified Supabase Auth user, unique |
| `email` | varchar(320) | |
| `display_name` | varchar(120) | |
| `role` | varchar(16) | `submitter` or `reviewer`, constrained in the database |
| `created_at` | timestamptz | |

`auth_user_id` is deliberately not a foreign key. Supabase owns the `auth.users` table and Django migrations must not reach into it.

### `app_submission`

One row per submitted document.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID | primary key |
| `title` | varchar(150) | required, trimmed before length is judged |
| `context` | text | optional, max 2000 characters |
| `submitted_by` | FK to profile | set from the verified session, never from the request body |
| `original_filename` | varchar(255) | display only, escaped when rendered |
| `storage_object_key` | varchar(300) | unique, generated, never derived from the filename |
| `file_size_bytes` | integer | |
| `content_type` | varchar(100) | what the bytes turned out to be |
| `status` | varchar(16) | `pending`, `approved` or `rejected` |
| `created_at` | timestamptz | indexed |
| `reviewed_by` | FK to profile, nullable | |
| `reviewed_at` | timestamptz, nullable | |
| `decision_note` | text | max 2000 characters |

### Why the storage key is generated

The filename comes from the user. If it were used as the storage path, a name containing slashes could write outside its own folder, and two people uploading `report.pdf` would collide. The key is `submissions/{profile_id}/{uuid}{extension}`, where the extension comes from what validation proved the bytes to be, not from the name.

The original filename is kept purely to show back to the person who uploaded it.

### Three database constraints, not just application checks

The database refuses to store an inconsistent record even if application code is wrong:

1. `status` must be one of the three values.
2. A pending row must have no reviewer and no review timestamp. A decided row must have both. There is no such thing as a half written decision.
3. A rejected row cannot have an empty note.

Application code enforces these too. The constraints exist because application code is where bugs live.

### Why there is no activity or audit table

The activity trail you see in the UI ("Submitted" and "Approved") is derived from `created_at`, `reviewed_at` and the two actor columns. A separate event table would be real infrastructure earning its keep only once a document can change more than once, which in this version it cannot.

This is a display convenience and **not** tamper proof auditing. Adding a genuine audit trail is listed under [production work](#what-i-would-add-for-production).

---

## State transitions

```
                   ┌─────────┐
    upload ───────▶│ pending │
                   └────┬────┘
                        │
            ┌───────────┴───────────┐
            │                       │
            ▼                       ▼
      ┌──────────┐            ┌──────────┐
      │ approved │            │ rejected │
      └──────────┘            └──────────┘
         (final)                 (final)
```

Exactly two transitions are legal, both out of `pending`. There is no reopening, no editing, no withdrawing and no resubmission.

That single rule is load bearing. It is why submissions can be immutable, why the conflict handling works the way it does, and why two timestamp columns are enough to express the whole history.

### How a decision is written

The naive version reads the row, checks it is pending, then saves. Between the read and the save, another reviewer can do exactly the same thing, and the second write silently overwrites the first.

Instead the decision is one conditional statement:

```sql
UPDATE app_submission
   SET status = ?, reviewed_by = ?, reviewed_at = ?, decision_note = ?
 WHERE id = ? AND status = 'pending'
```

Whoever's statement reaches the row first wins. The second matches zero rows, and the API returns `409` with the outcome that was actually saved, so the UI can show what really happened rather than guessing.

Disabling the button after a click does not solve this. The button is in a browser I do not control, and the race happens on the server.

This is tested properly, not assumed: five simultaneous approvals fired through a thread barrier against real PostgreSQL produce exactly one success and four conflicts.

---

## API design

All routes are under `/api/`. Everything except `/api/health/` requires `Authorization: Bearer <supabase access token>`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health/` | liveness, no auth, no database |
| GET | `/api/me/` | the verified caller and their role |
| GET | `/api/submissions/` | role scoped list with counts, optional `?status=` |
| POST | `/api/submissions/` | create, multipart, submitters only |
| GET | `/api/submissions/{id}/` | detail, if you are allowed to see it |
| GET | `/api/submissions/{id}/file-url/` | short lived signed read URL |
| POST | `/api/submissions/{id}/decision/` | approve or reject, reviewers only |

Every example below is a real response captured from the running API.

### GET /api/me/

The frontend needs to know where to send you after sign in. The token says who you are but carries no role, so the role has to come from the server.

```json
{
  "id": "d9d782df-36a0-4d73-a42e-81ed3c91453b",
  "email": "submitter-a@example.com",
  "display_name": "Alex Morgan",
  "role": "submitter"
}
```

### GET /api/submissions/?status=pending

```json
{
  "results": [
    {
      "id": "37fd83a7-4818-454c-9e57-f49ccc31168d",
      "title": "Expense claim, signed scan",
      "context": "",
      "status": "pending",
      "original_filename": "expense-claim-scan.png",
      "file_size_bytes": 34601,
      "content_type": "image/png",
      "created_at": "2026-10-24T11:51:53.270060Z",
      "submitted_by": {
        "id": "d9d782df-36a0-4d73-a42e-81ed3c91453b",
        "display_name": "Alex Morgan",
        "email": "submitter-a@example.com",
        "role": "submitter"
      },
      "reviewed_by": null,
      "reviewed_at": null,
      "decision_note": ""
    }
  ],
  "counts": { "pending": 5, "approved": 5, "rejected": 4, "all": 14 }
}
```

**Why counts ship with the list.** The UI shows a count on every filter tab. Deriving those from the filtered rows would make each tab report only its own size, which is wrong and a very easy mistake to make. The counts are computed from the caller's whole authorized set before any filter is applied, and there is a test asserting they do not change when `?status=` does.

**Why the response is an object and not a bare array.** It has room to grow. Pagination, if it is ever added, goes here without breaking clients.

**Ordering is role specific.** Reviewers get oldest first, because a queue should drain. Submitters get newest first, because they are tracking recent work. Both tie break on id so the order is deterministic when timestamps match.

### POST /api/submissions/

Multipart, with `title`, optional `context` and `file`.

```json
{
  "id": "09d27b47-b5d8-4f0f-aeb3-b85f270d7739",
  "title": "README example",
  "context": "Captured for documentation.",
  "status": "pending",
  "original_filename": "example.pdf",
  "file_size_bytes": 431,
  "content_type": "application/pdf",
  "created_at": "2026-10-24T12:28:09.183440Z",
  "submitted_by": {
    "id": "b374bd69-6322-4a21-a8a2-89942cb56c03",
    "display_name": "Priya Shah",
    "email": "submitter-b@example.com",
    "role": "submitter"
  },
  "reviewed_by": null,
  "reviewed_at": null,
  "decision_note": ""
}
```

**Ownership and status are not accepted from the client.** Sending `submitted_by` or `status` in the body has no effect: the owner comes from the verified session and the status is always `pending`. There is a test that sends both and asserts they are ignored.

**The file is validated by reading its bytes.** The filename extension and the browser's declared content type are both supplied by the client, so neither is evidence. A text file named `report.pdf` and declared `application/pdf` is refused, and a PNG named `report.pdf` is correctly stored as a PNG.

### GET /api/submissions/{id}/file-url/

```json
{
  "url": "https://<project>.supabase.co/storage/v1/object/sign/submissions/...?token=...",
  "expires_at": "2026-10-24T12:33:10.559598+00:00"
}
```

**Why this is a separate endpoint rather than a field on the submission.** A signed URL is a bearer link: anyone holding it can read the file until it expires. Putting it on the list response would mint one for every row whether or not anyone opens it, and those links would end up in logs, browser history and any cached response. Instead it is minted on demand, after the permission check, and never persisted.

The expiry is five minutes. The frontend fetches a fresh one each time rather than reusing an old one, because a cached link would eventually fail for no reason the user could understand.

### POST /api/submissions/{id}/decision/

```json
{ "decision": "approve", "note": "Looks correct." }
```

Returns the full updated submission, so the UI does not need a second request to show the outcome.

**Why `decision` is a verb and not a status.** The client says what it wants to do, not what the row should become. That keeps the state machine on the server where it belongs. A client sending `{"status": "approved"}` is asserting an outcome; a client sending `{"decision": "approve"}` is requesting an action the server may refuse.

### Errors

One shape everywhere:

```json
{
  "error": {
    "code": "rejection_note_required",
    "message": "A rejection must explain what is wrong.",
    "field_errors": { "note": ["Required when rejecting."] }
  }
}
```

`code` is stable and meant to be branched on. `message` is safe to show a user. `field_errors` appears when the problem belongs to specific fields.

Real examples from the running API:

| Status | Code | When |
| --- | --- | --- |
| 400 | `invalid_status_filter` | `?status=banana` |
| 400 | `rejection_note_required` | rejecting with a blank note |
| 400 | `office_open_xml` | a Word file, with advice to export as PDF |
| 401 | `authentication_required` | no token |
| 401 | `invalid_token` | expired or forged token |
| 403 | `forbidden` | submitter trying to decide |
| 403 | `profile_not_provisioned` | valid Supabase session, no application account |
| 404 | `not_found` | missing, or not yours |
| 409 | `already_decided` | someone decided first |
| 413 | `file_too_large` | over 5 MiB |
| 503 | `auth_unavailable` | Supabase Auth unreachable |
| 503 | `storage_unavailable` | Storage unreachable |

**Two of these deserve explanation.**

`404` rather than `403` when a submitter asks for someone else's document. A 403 would confirm the document exists, which leaks information. The response is identical to one for a document that was never created.

`503` rather than `401` when Supabase Auth is unreachable. These are completely different problems. Collapsing them would sign every user out during a provider outage and make them think their credentials were wrong. There is a test that points the auth client at a dead port and asserts a 503.

### No Swagger spec

The assessment lists it as a good to have. I did not add one. Seven endpoints with examples in a README is more readable than a generated spec, and adding a schema generator means a dependency and a build step that earn their keep at a size this project is not at. For a larger API I would generate one with `drf-spectacular`.

---

## Major decisions and trade-offs

### On the time budget

The assessment sets a two hour budget and explicitly allows mocking data and file storage to stay inside it.

**This build is considerably larger than that**, and I want to be straightforward about it rather than let it be discovered. I chose to build against real Supabase Auth, real private storage and real PostgreSQL, with no mocks anywhere including in the tests, and to take the security and concurrency questions seriously.

I think the result is worth more than a two hour version. But it is a deliberate departure from the brief, not an accident, and the trade-offs below are the ones I actually made rather than the ones a two hour build would have faced.

### Supabase rather than local file storage

Storing uploads on disk is simpler and would have been faster. It also does not survive a deploy on most hosts, does not work with more than one server process, and makes "who is allowed to read this file" a question with no good answer.

The cost is that the app now depends on a third party being up, and the tests are slower because they talk to it.

### No mocks, including in tests

The strongest argument for this is not philosophical. It is that it caught two real bugs:

**Supabase storage deletes fail silently.** `remove()` returns HTTP 200 with an empty list whether the object was deleted, never existed, or the bucket does not exist. It never raises. My cleanup code treated "did not throw" as success, so a failed cleanup looked identical to a successful one and the orphaned file would never have been reported. A mocked client programmed to raise an exception would have passed the test and hidden this permanently.

**A page that crashed while every API test passed.** The submissions list rendered blank because `Intl.DateTimeFormat` rejects `dateStyle` combined with `timeZoneName`. Backend tests were all green. Tests passing is not the same as the thing working.

The honest cost: the suite takes three and a half minutes instead of seconds, it needs network access, and it will fail if Supabase is having a bad day. Zero mocks does not make all testing better. It makes integration testing real and failure path testing harder.

### Accounts are provisioned, not self service

There is no sign-up page and no password reset.

The reason is roles. The security model rests on the server knowing that this account is a reviewer and that one is not, and that nobody can change that from the browser. Self service sign-up forces the question "what role does a stranger get", and any answer the user can influence is a hole.

The trade-off is real: a user who forgets their password has no way back in without an administrator. For a closed internal tool that is how most approval systems actually work, but it would not be acceptable for a public product.

### PDF and images only

A file is accepted only if a reviewer can read it **in the browser**. Browsers ship a PDF engine and an image decoder and nothing else.

Accepting a Word file would mean the reviewer downloads it, opens another application, reads it there, and comes back to decide. At that point it is not a review tool.

So Word, Excel and PowerPoint are refused with a message telling you to export as PDF, which is more useful than a refusal that only says no. SVG and HTML are refused outright because browsers execute them, which makes them an attack dressed as a document. GIF is refused too: the accepted list is an allowlist, not "anything the image library can open".

Images matter because the realistic non PDF document is a scan or a phone photograph of a signed form.

### Photo metadata is stripped

Photographs carry GPS coordinates, the device, and a timestamp. Someone submitting a phone photo of a signed form is unlikely to realise they are also submitting where they were standing.

This sits awkwardly against the principle that the stored file should be exactly what was submitted. I resolved it toward privacy, but carefully: JPEGs are re-saved reusing the original compression tables rather than re-compressed, so the visible image is pixel for pixel identical and only the metadata segments are removed. A test asserts that.

### Upload and database write are not atomic

A successful submission needs two things to happen in two different systems: the file must land in storage and the row must commit to PostgreSQL. They cannot share a transaction.

The order is upload first, then write the row. If the row fails, the uploaded object is deleted. If that cleanup also fails, a loud log entry names the object key so a human can remove it.

The reverse order would be worse. A row pointing at a file that does not exist is visible to users; an orphaned file is invisible to them.

**This is not atomic and I am not going to pretend it is.** Orphaned files remain possible. Fixing it properly means a reconciliation job, which is listed under production work.

### No pagination

With three accounts and a handful of documents, pagination is infrastructure with nothing to do. The list endpoint returns everything the caller is allowed to see.

Because there is no pagination, the counts are computed from the rows already fetched rather than with a second aggregate query, which saves a database round trip and makes the counts structurally unable to disagree with the data.

Both of those decisions stop being correct the moment the dataset grows. That is the trade-off, and it is written in a comment at the place it matters.

### The mockups show a larger product

The supplied designs include document versions, "request changes", resubmission, reviewer assignment, an approval route, due dates and a custom PDF toolbar.

None of that is built. I took the palette, the spacing, the type pairing and the layout, and left the features out, because building what the images showed would have quietly reintroduced a much bigger product than the one specified. The visual language matches; the feature set is deliberately smaller.

---

## Security notes

### The one worth reading

**Supabase exposes every table you create through an auto generated REST API, and grants the anonymous role full access to new tables in the `public` schema by default.** Django creates its tables there.

Measured on this project before it was fixed: the `anon` role held `SELECT`, `INSERT`, `UPDATE`, `DELETE` and `TRUNCATE` on both application tables, with row level security disabled. Using only the publishable key, which ships inside the JavaScript bundle and is readable by any visitor, it was possible to:

- read every submission
- delete or truncate all of them
- insert fabricated approved records
- run `UPDATE app_profile SET role = 'reviewer'` and grant yourself reviewer access

That last one defeats every authorization check in the product, because the Data API bypasses Django entirely.

Nothing in the application code was wrong. It was a platform default meeting an ORM default.

Migration `0002_lock_down_data_api` revokes all privileges on tables, sequences and functions in `public` from `anon` and `authenticated`, revokes schema usage, alters default privileges so future migrations do not re-inherit the grants, and enables row level security on both tables. Django connects as the table owner, which is exempt, so the application is unaffected.

The reverse migration deliberately does not restore those grants. Undoing a security fix should not hand `TRUNCATE` back to anonymous users.

There are now tests that fail loudly if this ever reopens.

### The rest

- **Files are private.** Verified that the public path, an unauthenticated request, and a request carrying the browser's own publishable key are all refused. A valid signed URL works; an expired one and one with a single altered character do not.
- **Cross user access is denied at the API, not just in the UI.** Using one submitter's real token against another's document: read returns 404, file URL returns 404, decide returns 403.
- **Secrets stay on the backend.** The test suite greps the production bundle for the secret key, database password and Django key on every run.
- **Uploads are validated by content**, never by filename or declared type.
- **The frontend route guard is usability, not security.** The server re-checks the role on every request, so typing a URL directly gains nothing.

### What this is not

Validating that a file is a well formed PDF is not malware scanning. A perfectly valid PDF can be malicious. Scanning is listed under production work.

---

## Performance

I measured rather than guessed. All figures are medians, from a laptop to a Supabase project in `ap-northeast-2` (Seoul).

| Endpoint | Before | After |
| --- | --- | --- |
| `GET /api/health/` | 1301 ms | 6 ms |
| `GET /api/me/` | 1289 ms | 522 ms |
| `GET /api/submissions/` | 1640 ms | 673 ms |
| Reviewer detail, click to usable | 1980 ms | 941 ms |

Four causes, in order of size:

**Django was reconnecting to the database on every request.** `CONN_MAX_AGE` was 0, so every request paid a fresh TCP and TLS handshake across the Pacific: about 950 ms of pure overhead. Now 600 seconds with health checks.

This is invisible under `manage.py runserver`, which spawns a thread per request while Django keeps connections per thread, so nothing is reused. It only shows under gunicorn. If you benchmark this app with `runserver`, you will measure the wrong thing.

**The health check was doing the two slowest things in the app.** DRF runs authentication whenever a token is present, even where the permission class allows anyone, so a liveness probe was verifying a token with Supabase and loading a profile from the database. It now skips authentication entirely. This matters beyond speed: a health check that depends on Auth and the database reports your service as down whenever either is slow.

**The list endpoint made two database round trips** where one would do, because the counts came from a separate aggregate query.

**The reviewer detail page fetched its document and its preview link one after the other**, though neither depends on the other. Both now go at once. Note that this is worth nothing with a single worker, where the two requests simply queue; the gain is real only because production runs two.

The remaining large cost is a 188 ms call to Supabase Auth on every authenticated request, discussed under production work.

---

## AI tools used

I built this with **Claude (Anthropic)**, used throughout rather than for one task. Being specific about how, since "used AI for scaffolding" tells you nothing:

**Scaffolding and boilerplate.** Django project layout, settings, the React app structure, CSS. Ordinary code generation where the shape is known.

**Research against live documentation.** Supabase's free tier project limits, whether the Data API can be disabled, Render's free tier behaviour, Django's Python version support, package peer dependency ranges. This was genuinely useful and prevented several wrong assumptions, including picking frontend versions that would not have worked together.

**Measurement and diagnosis.** The performance work above was done by instrumenting and measuring, not by guessing. The Data API vulnerability was found by querying the live grants rather than assuming the defaults were safe.

**Writing tests**, particularly the awkward ones: the thread barrier for the concurrency check, and inducing real failures (a dead port for the auth outage, a non existent bucket for storage failure, a genuine constraint violation for a database failure after upload).

**Debugging.** Several bugs in this build were found and fixed with it, including ones it had introduced itself. Two examples, both recorded in the decision log: a React effect that cancelled its own timer so a highlight never cleared, and a measurement that appeared to show a frozen animation but was actually reading a detached DOM node.

**What I verified myself.** Every claim in this README about behaviour was checked by running it. The browser flows were driven manually, both roles, both submitters. Where something is unverified, this README says so.

`docs/decision-log.md` is the full record, written as the work happened, including the mistakes and the corrections.

---

## What I would add for production

Roughly in the order I would do them.

### Correctness and safety

**Malware scanning on upload.** Structural validation is not scanning. A clean PDF can still be hostile. ClamAV or a hosted scanner, before the file is ever served.

**A reconciliation job for orphaned files.** The compensating cleanup narrows the window where an upload succeeds and its row does not; it cannot close it. A scheduled sweep comparing the bucket against the database would, and it should alert rather than delete silently.

**Rate limiting.** There is none. Upload and decision endpoints are the obvious targets.

**A retention policy.** Documents currently live forever. Real systems need an answer to how long, and a deletion path that removes both the row and the object.

### Operations

**Observability.** Structured logging with request ids, error tracking such as Sentry, and an alert when the orphaned object warning fires. Right now that warning goes to a log nobody is watching, which makes it nearly useless.

**CI.** Run `./scripts/test.sh` on every push against a dedicated test project.

**Backups and a restore drill.** Supabase's free tier has none. A backup you have never restored is a hope.

### Scale

**Pagination,** and with it the counts move back to an aggregate query.

**Local JWT verification.** Every authenticated request currently makes a 188 ms call to Supabase Auth. This project already issues ES256 tokens and publishes a JWKS, so Django could verify signatures in process with no network call. The trade-off is that a revoked session would stay valid until the token expires, where today revocation is immediate. Worth doing with a short cache and a documented revocation story.

**Code splitting.** The bundle is 519 kB raw, 150 kB gzipped, mostly the Supabase client.

### Product

**A real audit trail.** The current two event display is derived from two timestamp columns. It shows the state, not the history that produced it. For an approval system that is the first thing a compliance review asks about.

**Notifications.** Right now a reviewer has to come and look. Email on new submission and on decision, which also means an email provider and a bounce story.

**Office document support**, if the use case demands it. Browsers cannot render Word, Excel or PowerPoint, so there are two routes:

*Server side conversion to PDF* with LibreOffice headless, triggered by a background job or lazily on first view with the result cached. The original stays the record of what was submitted and the PDF is a derived preview. This is what Google Drive and Dropbox do. It needs a worker, several hundred megabytes of dependency, and sandboxing with memory limits and timeouts, because converters that parse hostile formats are a classic source of vulnerabilities. The converter becomes the risk, not the conversion.

*Client side rendering* with a library such as `docx-preview`, which keeps the file private and needs no infrastructure, at the cost of approximate layout. For an approval tool that matters: approving a contract whose signature block did not render is a genuine risk.

Excel is the exception to both. Converting a spreadsheet to pages loses the formulas behind the numbers and slices wide sheets arbitrarily. Spreadsheets need a grid viewer, not a different converter.

**Accessibility beyond what was checked.** Contrast is verified by calculation across 17 colour pairs and keyboard paths were exercised by hand, but there has been no screen reader testing, no 200 percent zoom check, and no forced colours mode.

---

## Known limitations

Stated plainly, because finding these yourself is worse than reading them here.

- **No automated browser test.** All UI verification was done by driving the browser manually, both roles and both submitters. That is real evidence but it is not reproducible by running the test command. One happy path Playwright test is the obvious next addition.
- **Frontend tests are pure functions and renders only.** Nothing exercises a component talking to the API.
- **Not atomic across storage and database.** Orphaned files remain possible.
- **No pagination**, and the counts optimisation depends on that.
- **Decisions are final.** No reopening, no resubmission, no versions.
- **Free tier behaviour.** Render's free web services sleep after 15 minutes and take about a minute to wake, so a first request after idle is slow. The frontend detects this and says the server may be waking rather than spinning silently. Supabase free projects pause after a week of inactivity.
- **The tests need real credentials** and will not run without them.

---

## Effort

The assessment sets a two hour budget. **This took considerably longer**, spread across one extended working session.

I do not have a reliable hour by hour figure and I am not going to invent one. What I can state precisely: the test suite takes about three and a half minutes per run, the work proceeded in six phases, and `docs/decision-log.md` records each decision at the point it was made, including the ones that turned out to be wrong.

The extra time went into the real integrations, the no mocks test suite, the security audit that found the Data API exposure, the concurrency work, and the measured performance pass. A two hour version would have mocked storage, skipped the concurrency question, and never found the Data API problem.
