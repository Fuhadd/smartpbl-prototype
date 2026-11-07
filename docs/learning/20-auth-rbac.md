# 20 — Authentication and role-based access control

## 1. What was built

| File | Purpose |
|---|---|
| `app/core/security.py` | Argon2id password hashing (pwdlib) with a dummy-hash check for unknown users, plus JWT encode/decode (PyJWT). Decoding pins HS256 and requires `exp, iat, iss, aud, sub, jti, type`. A refresh token is never accepted as an access token, or the reverse |
| `app/auth/models.py` | `users` (username, hash, role, `is_active`) and `refresh_tokens` (jti, family, expiry, `revoked_at`, `replaced_by`). Migration `0005` |
| `app/auth/permissions.py` | `Permission` enum and the **role → permissions table**, the whole access policy in one place |
| `app/auth/service.py` | `authenticate`, `issue_tokens`, `rotate` (single-use refresh tokens with **reuse detection**), `logout` (revokes the session's token family) |
| `app/api/deps.py` | `get_current_user` (bearer token → active user, **reloaded from the DB on every request**) and `require(permission)`, which gives 401 or 403. Replaces the `X-Reviewer` header |
| `app/api/auth.py` | `POST /auth/token` (OAuth2 password form), `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` |
| `app/api/{notes,review,audit,schedule,workforce}.py` | Each router authenticates at router level, and each endpoint declares its permission. Reviewer, solver-requester and viewer identities now come from the token. Workforce audit actors are `user:<name>`, like the others |
| `app/core/db.py` | `string_enum` moved here from `nlp/models.py`, so auth can share it |
| `app/main.py` | `ROUTERS` tuple (the route-guard test walks it) |
| `scripts/create_user.py` | Creates an account. The password is prompted for or read from stdin, never passed as an argument; minimum 12 characters |
| `tests/test_security.py` | 15 unit tests: Argon2id format and salting; expiry; type confusion; forged tokens (other key, HS512, wrong `aud`/`iss`, missing claims, `alg: none`, garbage); a tampered payload |
| `tests/test_auth_api.py` | 54 tests: login, identical failure responses, immediate effect of disabling or demoting, rotation, reuse detection, logout. Also the **route × role matrix** (10 routes × 3 roles, plus unauthenticated), a guard that every route declares a permission, and a check that authorisation runs before expensive dependencies |
| `tests/conftest.py` + 3 API test files | An `auth_headers(role)` fixture; the existing tests now use real bearer tokens |

Test count: 233 → **301**. Live check (`uvicorn` + `curl`): login 200; `/auth/me` gives the role and permissions; a coordinator on `/workforce/risk` gets 403; no token gets 401; rotation gives 200, then replaying the old refresh token gives 401 and revokes both rows in the family. Unknown-user and wrong-password logins both took about 0.05 s.

## 2. Why this way

- **Authorise from the database, not the token.** The access token carries `role`, but only so clients can draw role-aware screens (Tier 5). On every request the server loads the user by `sub` and checks `is_active` and the *current* role. A carer who leaves, or a coordinator moved off duty, loses access on their next request, not 15 minutes later. The cost is one primary-key lookup per request, on a session the request already opens. A test demotes a user mid-session and gets 403 with the same token.
- **Short access tokens plus rotating refresh tokens.** Access tokens last 15 minutes and are never stored. Refresh tokens last 7 days and are single use: each refresh revokes the presented token and issues a new one in the same *family* (one login session). RFC 9700 §4.14.2 describes rotation this way. If an invalidated refresh token comes back, two parties hold it and the server can't tell which one is legitimate, so it revokes the whole family. A carer's phone stolen from a car is the realistic threat.
- **Refresh tokens are JWTs, but stateful.** The plan asked for JWT refresh tokens. A JWT alone can't be revoked, so I store each one's `jti` (never the token) and check it on use. The signature rejects forgeries without a database hit. The row gives revocation, rotation lineage (`replaced_by`) and row-locked concurrency: `SELECT … FOR UPDATE` means two simultaneous refreshes can't both win.
- **Permissions, not roles, in routes.** Endpoints say `require(Permission.REVIEW_DECIDE)`, and one table maps roles to permissions. The policy is reviewable in one screen, and changing it doesn't touch routers. The defaults follow least privilege and separation of duties:

  | Permission | Carer | Coordinator | Manager |
  |---|:-:|:-:|:-:|
  | Create note | ✓ | ✓ | |
  | Read note, review queue, schedule | | ✓ | ✓ |
  | Decide review flags, run solver | | ✓ | |
  | Read audit trail, workforce risk | | | ✓ |

  Managers oversee but don't act. Coordinators act but can't read attrition scores, as the model card requires, or the audit trail. Carers can only submit notes for now. Reading their own notes needs object-level checks (OWASP API1, BOLA), which arrive with the carer app.
- **Deny by default, enforced by tests.** OWASP API5:2023 says access "should deny all access by default, requiring explicit grants to specific roles". Three tests make a forgotten check fail CI:
  - **Guard test:** every operation in the OpenAPI schema, except `/health` and the login endpoints, has bearer security and a `require(...)` dependency.
  - **Matrix test:** a literal table of allowed roles per route, written independently of `ROLE_PERMISSIONS` so the test isn't circular, is checked for every role.
  - **Coverage test:** the matrix lists every route.

  I mutation-tested this by removing the audit endpoint's permission: three tests failed.
- **One failure response.** An unknown user, a wrong password and a disabled account all return the same 401 body. Unknown users still pay for one Argon2 verification against a dummy hash, so timing doesn't reveal which usernames exist (the FastAPI tutorial's pattern). Every token failure (expired, forged, wrong type) is the same 401 with `WWW-Authenticate: Bearer`.
- **Authentication runs before anything expensive.** Each router has `dependencies=[Depends(get_current_user)]`, and FastAPI solves those before the endpoint's own dependencies and parameters. An unauthenticated caller can't trigger the 4-second model training, and can't probe validation rules, because they get 401 before any 422. A test overrides `get_workforce` and asserts that a coordinator's 403 never calls it.
- **Argon2id via pwdlib, as the current FastAPI tutorial recommends.** pwdlib's defaults (m = 64 MiB, t = 3, p = 4; about 33 ms per verify here) exceed OWASP's minimum of 19 MiB, t = 2, p = 1. Argon2 is *memory-hard*: each guess needs 64 MiB, which makes GPU cracking of a stolen `users` table expensive.

## 3. Alternatives considered

| Option | Pros | Cons | When I'd choose it |
|---|---|---|---|
| **Short JWT access + rotating, DB-tracked JWT refresh (chosen)** | Stateless signature checks; revocable sessions; reuse detection; works for both browser and mobile clients | Access tokens can't be revoked for up to 15 min after logout; a shared HS256 secret | A single API with first-party clients |
| Opaque server-side session tokens (random id → DB row) | Instantly revocable; nothing to forge; simplest correct design | A DB lookup per request (we do one anyway); not what the plan specified | Honestly fine here. I'd pick it if JWT weren't a requirement |
| External identity provider (Microsoft Entra ID / Keycloak, OIDC) | SSO with staff Microsoft 365 accounts; MFA, lockout and joiner/leaver handling done by the IdP; asymmetric RS256 keys | An external dependency; tenancy and config work; harder offline demos | **Production at PBL.** Staff already have work accounts, and the provider's leaver process then cuts API access automatically |
| RS256 (asymmetric) signing in-house | Other services can verify with the public key only; key rotation via JWKS | Key management for one service is overkill | Several services verifying tokens |

## 4. How it works

**A JWT is three base64url parts:** `header.payload.signature`.

    header   {"alg": "HS256", "typ": "JWT"}
    payload  {"role": "coordinator", "iss": "smartpbl-api", "aud": "smartpbl-clients",
              "sub": "5aa4…", "jti": "e0f1…", "type": "access", "iat": 1794041231, "exp": 1794042131}
    signature = HMAC-SHA256(secret, base64url(header) + "." + base64url(payload))

The payload is *encoded, not encrypted*: anyone can read it, so it holds no personal data beyond a UUID and a role. Integrity comes from the HMAC. Change `"carer"` to `"manager"` and the signature no longer matches; the tamper test does exactly this. `exp − iat = 900 s`.

**Why `algorithms=["HS256"]` matters.** The header names an algorithm, but the header is attacker-controlled. If the server trusted it, a token with `"alg": "none"` and no signature would verify. RFC 8725 §3.1: libraries "MUST enable the caller to specify a supported set of algorithms". The test suite includes an `alg: none` token and an HS512 token signed with the real key; both are rejected.

**Why a `type` claim.** Access and refresh tokens share a key, issuer and audience. Without `type`, a 7-day refresh token would work as a 7-day access token. RFC 8725 §2.8 calls this cross-JWT confusion, and §3.12 asks for validation rules that are mutually exclusive between token kinds.

```mermaid
sequenceDiagram
  participant App as Carer app
  participant API as FastAPI
  participant DB as Postgres
  App->>API: POST /auth/token (username, password)
  API->>DB: SELECT user; Argon2 verify
  API->>DB: INSERT refresh_tokens (jti=R1, family=F)
  API-->>App: access A1 (15 min), refresh R1 (7 days)
  App->>API: GET /review/queue  Bearer A1
  API->>DB: SELECT user by sub (active? role?)
  API-->>App: 200 / 403
  Note over App: A1 expires
  App->>API: POST /auth/refresh R1
  API->>DB: SELECT R1 FOR UPDATE; revoke R1; INSERT R2 (family F); R1.replaced_by=R2
  API-->>App: A2, R2
  Note over API: attacker replays stolen R1
  API->>DB: R1 already revoked → revoke all of family F (R2 too); COMMIT
  API-->>App: 401 (both thief and owner must log in again)
```

**401 vs 403.** 401 means "I don't know who you are" (missing, invalid or expired token; the client should log in or refresh). 403 means "I know who you are, and you may not do this" (re-authenticating won't help). The matrix test asserts exactly 403 for the wrong role, and anything but 401/403 for the right one.

## 5. Interview questions and answers

**Q1. Walk me through how a request is authorised.**
The client sends `Authorization: Bearer <access token>`. A router-level dependency decodes it with the algorithm pinned to HS256, checks the signature, expiry, issuer, audience, required claims and that it's an access token. It then loads the user by `sub` and rejects missing or disabled accounts with 401. The endpoint's `require(permission)` dependency checks the user's current role against the permission table and returns 403 if it's not granted. All of this runs before any body validation or expensive dependency. The authenticated username is then what goes into the audit log and the reviewer-decision table, instead of a client-supplied header.

**Q2. JWTs are "stateless". Why do you hit the database on every request anyway?**
To make revocation real. A purely stateless check would keep a dismissed carer's token working until it expired, and would keep authorising an old role after a demotion. Loading the user is one indexed primary-key read on a session the request already has, which is negligible next to an LLM call or a solver run. The token's signature still does useful work: forged and expired tokens are rejected without touching the database. If load ever mattered, I'd cache user state for a few seconds, a deliberate, small revocation delay.

**Q3. Explain refresh-token rotation and reuse detection.**
Each refresh token is single use. Exchanging it revokes it, issues a new one in the same family and records the link. If an already-used token is presented again, two parties must hold it, and the server can't tell which is legitimate. RFC 9700 says to revoke the active refresh token, so I revoke the whole family. The thief's fresh token dies with the owner's, and the owner logs in again. The revocation is committed before returning 401, and the refresh row is locked with `SELECT … FOR UPDATE`, so two concurrent refreshes can't both succeed.

**Q4. Trade-off: why not just use opaque server-side sessions?**
They'd be simpler and instantly revocable, and since I look up the user on every request anyway, the main JWT advantage is small here. The plan specified JWTs. They also give clients a readable, signed role claim for UI routing, and they'd let other services verify tokens without a session store if the system splits later. I'm honest that for one API with first-party clients, opaque sessions are an equally defensible choice, and I'd accept either in a design review.

**Q5. How did you decide who can do what?**
Least privilege and separation of duties, from the care workflow:
- **Carers** submit notes.
- **Coordinators** run the day: review flags and plan rotas.
- **Managers** oversee: read the audit trail and workforce risk, but don't decide flags or run the solver.

Coordinators are kept out of attrition scores because the model card restricts them to managers' supportive use. The policy is one role → permission table, and a test with an independently written route × role matrix pins it, so widening a permission is a visible, reviewed change. I verified that by granting coordinators audit access: exactly one matrix test failed.

**Q6. How do you stop someone enumerating usernames or brute-forcing passwords?**
Enumeration: every login failure returns the identical 401 body, and unknown usernames still run one Argon2 verification against a dummy hash, so response time doesn't leak existence. Brute force: Argon2id with 64 MiB and three passes makes offline cracking of a leaked table expensive, and a 12-character minimum length is enforced at account creation. The missing piece is online throttling: per-account and per-IP rate limits on `/auth/token`, stricter than general API limits, as OWASP API2 advises. That's Step 4.3, along with refusing to start with the default signing secret.

**Q7. With real PBL staff, what would you change?**
I'd delegate authentication to the provider's identity system, most likely Microsoft Entra ID via OpenID Connect. Staff then use their existing work accounts with MFA, and the joiner/leaver process disables API access automatically. The API would verify RS256 tokens against the IdP's published keys and map IdP groups to these same roles, so the permission table and the matrix tests stay. I'd also add per-patch scoping (a coordinator sees only their branch's clients and carers), carer self-access to their own data, and login and permission-denied events in the audit log.

**Q8. Where should a browser client keep these tokens?**
It's a trade-off for Step 4.3. In memory or `localStorage`, a script injected by an XSS bug can read them. In an `httpOnly` cookie, scripts can't read the token, but cookies are sent automatically, so you need `SameSite` and CSRF protection. My plan: the React dashboard keeps the access token in memory and the refresh token in an `httpOnly`, `Secure`, `SameSite=Strict` cookie scoped to `/auth/refresh`. The Flutter app stores the refresh token in the platform's secure storage (Keychain/Keystore). The API currently returns both tokens in the body, which serves the mobile client; the cookie variant comes with CORS in 4.3.

## 6. Learn more

**Official documentation**
- FastAPI, [OAuth2 with Password (and hashing), Bearer with JWT tokens](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/): the PyJWT + `pwdlib[argon2]` setup and the dummy-hash timing defence used here.
- PyJWT, [Usage examples](https://pyjwt.readthedocs.io/en/stable/usage.html): `algorithms=`, `options={"require": [...]}`, audience and issuer checks.
- OWASP, [API2:2023 Broken Authentication](https://api-security.owasp.org/editions/2023/en/0xa2-broken-authentication) and [API5:2023 Broken Function Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization): `alg: none`, expiry checks, brute force, and deny-by-default role checks.
- IETF, [RFC 9700 OAuth 2.0 Security BCP](https://www.rfc-editor.org/rfc/rfc9700.html) (§4.14.2, refresh token rotation) and [RFC 8725 JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html) (§3.1, algorithm verification; §2.8/3.12, cross-JWT confusion). Also the OWASP [Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) (Argon2id minimums).

**Videos**
- **"How NOT to Store Passwords!"**, Computerphile: [youtube.com/watch?v=8ZtInClXe1Q](https://www.youtube.com/watch?v=8ZtInClXe1Q). About 10 minutes on plain text vs hashing vs salting; the motivation for a slow, salted hash like Argon2.
- **"An Illustrated Guide to OAuth and OpenID Connect"**: [youtube.com/watch?v=t18YB3xDfXI](https://www.youtube.com/watch?v=t18YB3xDfXI). About 16 minutes, the background for the Entra ID/OIDC answer in Q7. The title is verified; search listings attribute it to the OktaDev channel, but the channel name wasn't visible on the fetched page.

## 7. Check your understanding

In `app/auth/permissions.py`, add `P.AUDIT_READ` to the coordinator's set. **Predict:** which tests fail, and with what status code?

```bash
uv run pytest tests/test_auth_api.py -q
```

**Expected (verified):** exactly **one** failure, `test_role_permission_matrix[GET /audit/{note_id}-coordinator]`, with `assert 404 == 403`. The coordinator now passes authorisation and reaches the endpoint, which finds no events for a random note id. The guard and coverage tests still pass, because the route still declares *a* permission. Only the independently written matrix notices that the *policy* changed. That's why it's a literal table, not derived from `ROLE_PERMISSIONS`. Revert the change afterwards.
