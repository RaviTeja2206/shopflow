What you just built and why it matters in interviews
Before moving to product service, let me summarize the decisions you made and defended through actual bugs — this is your interview material:
Decision 1 — Two token types with different lifetimes
Access token lives 30 minutes, stateless, no DB lookup per request. Refresh token lives 7 days, stored in DB, used only to get new access tokens. The tradeoff: speed vs revocability.
Decision 2 — Refresh tokens stored as hashes
If your database is breached, attackers get SHA-256 hashes. Without the original token string, the hash is useless. Same principle as password hashing.
Decision 3 — Token rotation
Every refresh call revokes the old token and issues a new one. A stolen token becomes detectable the moment the legitimate user next refreshes.
Decision 4 — Replay attack → nuclear revocation
When a revoked token is reused, we don't just reject it — we revoke every active session for that user. This limits the damage window to zero even if the attacker got refresh_token_2.
Decision 5 — Explicit commit before HTTPException
You found this bug yourself by testing. HTTPException is a subclass of Exception — our session middleware rolls back on any exception. Security-critical writes need await db.commit() before raising.
Decision 6 — Redis blocklist for access tokens
JWTs are stateless so they can't be "cancelled" — but storing their jti in Redis with a TTL matching their expiry gives you instant revocation on logout at the cost of one Redis read per authenticated request.


What you've built and debugged in this test session
This is genuinely valuable interview material. You didn't just write tests — you debugged three distinct infrastructure problems:
Problem 1 — localhost vs postgres: Inside Docker, services talk by name not localhost. Fundamental Docker networking concept.
Problem 2 — Event loop mismatch: asyncpg connections are bound to the event loop that created them. Session-scoped fixtures must share a session-scoped loop. Fixed with asyncio_default_test_loop_scope = "session".
Problem 3 — Transaction isolation vs production behavior: The _revoke_all_tokens_and_commit method calls await db.commit() explicitly. A test session wrapped in a single transaction saw this commit but then the outer test transaction conflicted. Solution: mirror production's per-request commit pattern in tests.
Problem 4 — Mock import paths: Mocking app.core.redis.get_redis doesn't cover get_current_user which imported get_redis separately. Mock every import path where the function is used.