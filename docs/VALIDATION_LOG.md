# Camera Runtime v1 — Validation Log

Master validation record for the first end-to-end manual UI validation
effort. One entry per issue discovered during testing, appended below in
the format below. Camera Runtime v1 is not declared production-ready
until every entry in this log reaches a closed `Status`.

---

Date/Time

Environment

Validation Mode

Steps to Reproduce

Expected Behaviour

Actual Behaviour

Relevant Logs

Root Cause

Fix

Commit

Regression Test Added

Status

---

Date/Time

2026-07-29

Environment

Local dev sandbox, launched via `python run.py --validation`

Validation Mode

Enabled

Steps to Reproduce

1. `python run.py --validation` from repo root.
2. Wait for all three services to report healthy.
3. In the browser, log in with `testadmin` / `TestPass123!`.

Expected Behaviour

Login succeeds; API returns a token pair.

Actual Behaviour

Login returns "Invalid username or password"; API responds HTTP 401.

Relevant Logs

`POST /auth/login` → `401 Unauthorized`, `{"code":"unauthorized","message":"Invalid username or password"}`. Direct DB query: `UserRepository.get_by_username('testadmin')` → `None`; `UserRepository.list()` → 0 total users. `alembic current` → `9c1f6b4a2e7d (head)` (schema already fully migrated, not stale).

Root Cause

Not a code defect. `testadmin` was created earlier in this same development effort via `scripts/create_test_user.py`, but this sandbox's PostgreSQL data does not persist across an environment reset boundary that recurred repeatedly over the course of this project (confirmed independently several times: `alembic upgrade head` had to run from empty — `-> 3bb1f0f0a294, initial schema` — on multiple separate occasions rather than reporting "already at head"). One such reset wiped the `users` table (and every other table) after the account was created. The full authentication chain (Frontend → API → `LocalUserAuthProvider.authenticate()` → `UserRepository.get_by_username()` → `verify_password()`/bcrypt → `create_token_pair()`) was verified correct end-to-end at the code level; it fails exactly and only at the user-lookup step because the row does not exist, which is the documented, correct behavior for that case. Not a wrong database, not a launcher environment mismatch, not a `create_test_user.py` configuration issue, and not an uncommitted transaction — confirmed by direct inspection, not assumption.

Fix

`run.py` now calls a new `ensure_test_user()` (`scripts/create_test_user.py`) on every startup, after migrations: create-if-missing only, never touches an existing user's password or role. Distinct from the existing `create_test_user()` CLI function, which is left unchanged (it still overwrites on explicit re-run — a deliberate, operator-invoked convenience for resetting a forgotten local password by hand). Prints `Development administrator created` or `Development administrator verified` depending on which happened.

Commit

`cd72732`

Regression Test Added

Hardware-verified (no automated regression test — this behavior depends on real Postgres state, matching this repo's established convention of hardware-validating environment-dependent behavior rather than mocking it): (1) fresh run with no `testadmin` row → "created", login succeeds; (2) second run with the row present → "verified", zero new rows (`UserRepository.list()` still returns exactly 1 user); (3) password changed directly in the database between runs, then launcher re-run → still "verified", the changed password still works, the default password no longer does — proving the account is never overwritten once it exists.

Status

Closed
