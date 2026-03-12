# Authentication & Authorization — Complete Guide with FastAPI

---

## Table of Contents

1. [Authentication vs Authorization](#1-authentication-vs-authorization)
2. [Basic Authentication](#2-basic-authentication)
3. [Session-Based Authentication](#3-session-based-authentication)
4. [Cookie-Based Authentication](#4-cookie-based-authentication)
5. [JWT Authentication](#5-jwt-authentication)
   - 5.1 [Access Token](#51-access-token)
   - 5.2 [Refresh Token](#52-refresh-token)
   - 5.3 [ID Token (OIDC)](#53-id-token-oidc)
   - 5.4 [Token Rotation](#54-token-rotation)
6. [API Key Authentication](#6-api-key-authentication)
7. [OAuth2](#7-oauth2)
8. [Role-Based Access Control (RBAC)](#8-role-based-access-control-rbac)
9. [Scenario Reference Table](#9-scenario-reference-table)
10. [Security Best Practices](#10-security-best-practices)

---

## 1. Authentication vs Authorization

```
┌─────────────────────────────────────────────────────────────┐
│                          REQUEST                            │
└─────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
           ┌───────────────────────┐
           │   AUTHENTICATION      │  "Who are you?"
           │  Verify Identity      │  → Username/Password
           │                       │  → Token / Key
           └───────────┬───────────┘
                       │ Identity confirmed
                       ▼
           ┌───────────────────────┐
           │   AUTHORIZATION       │  "What can you do?"
           │  Verify Permissions   │  → Role (admin, user)
           │                       │  → Scope (read, write)
           └───────────┬───────────┘
                       │ Access granted / denied
                       ▼
                   RESOURCE
```

| Concept        | Question          | Example                              |
|----------------|-------------------|--------------------------------------|
| Authentication | Who are you?      | Login with email + password          |
| Authorization  | What can you do?  | Admin can delete; User can only read |

---

## 2. Basic Authentication

Credentials (`username:password`) are Base64-encoded and sent in every request header.

### How it works

```
Client                              Server
  │                                   │
  │  GET /resource                    │
  │  Authorization: Basic dXNlcjpwYXNz│
  │──────────────────────────────────►│
  │                                   │  Base64 decode
  │                                   │  → "user:pass"
  │                                   │  Check DB
  │◄──────────────────────────────────│
  │  200 OK / 401 Unauthorized        │
```

> **No session is stored** — credentials are sent on EVERY request.

### FastAPI Implementation

```python
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

app = FastAPI()
security = HTTPBasic()

USERS = {
    "alice": "secret123",
    "bob": "password456",
}

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    stored_password = USERS.get(credentials.username)
    if not stored_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Use secrets.compare_digest to prevent timing attacks
    is_valid = secrets.compare_digest(
        credentials.password.encode(), stored_password.encode()
    )
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return credentials.username

@app.get("/resource")
def get_resource(user: str = Depends(authenticate)):
    return {"message": f"Hello, {user}"}
```

### When to use
- Internal tools / admin scripts
- Simple CLI → API calls
- NOT suitable for user-facing web apps (credentials re-sent every time)

---

## 3. Session-Based Authentication

The server creates and stores a **session** after login. The client holds only a **Session ID** (in a cookie). The server maps Session ID → user data.

### Flow

```
  CLIENT                          SERVER                      DB / Cache
    │                               │                            │
    │  POST /login {user, pass}     │                            │
    │──────────────────────────────►│                            │
    │                               │  Verify credentials ──────►│
    │                               │◄─────────────────── OK ───│
    │                               │  Create Session            │
    │                               │  session_id = "abc123"     │
    │                               │  Store: {abc123: user_id}─►│
    │◄──────────────────────────────│                            │
    │  Set-Cookie: session_id=abc123│                            │
    │                               │                            │
    │  GET /dashboard               │                            │
    │  Cookie: session_id=abc123    │                            │
    │──────────────────────────────►│                            │
    │                               │  Lookup session_id ───────►│
    │                               │◄──────── user_id=7 ───────│
    │◄──────────────────────────────│                            │
    │  200 OK  (dashboard data)     │                            │
    │                               │                            │
    │  POST /logout                 │                            │
    │──────────────────────────────►│                            │
    │                               │  Delete session ──────────►│
    │◄──────────────────────────────│                            │
    │  Clear-Cookie                 │                            │
```

### FastAPI Implementation (with Redis)

```python
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from redis import Redis
import uuid, hashlib

app = FastAPI()
redis = Redis(host="localhost", port=6379, decode_responses=True)

USERS = {"alice": hashlib.sha256(b"secret").hexdigest()}

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ─── Login ────────────────────────────────────────────────────────────────────
@app.post("/login")
def login(username: str, password: str, response: Response):
    stored = USERS.get(username)
    if not stored or stored != hash_password(password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session_id = str(uuid.uuid4())
    redis.setex(f"session:{session_id}", 3600, username)  # TTL = 1 hour

    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,   # JS cannot read it
        secure=True,     # HTTPS only
        samesite="lax",  # CSRF protection
    )
    return {"message": "Logged in"}

# ─── Auth dependency ──────────────────────────────────────────────────────────
def get_current_user(request: Request) -> str:
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username = redis.get(f"session:{session_id}")
    if not username:
        raise HTTPException(status_code=401, detail="Session expired")
    return username

# ─── Protected route ──────────────────────────────────────────────────────────
@app.get("/dashboard")
def dashboard(user: str = Depends(get_current_user)):
    return {"message": f"Welcome {user}"}

# ─── Logout ───────────────────────────────────────────────────────────────────
@app.post("/logout")
def logout(request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if session_id:
        redis.delete(f"session:{session_id}")
    response.delete_cookie("session_id")
    return {"message": "Logged out"}
```

### Key Properties

| Property         | Detail                                       |
|------------------|----------------------------------------------|
| State            | Stored SERVER-side (Redis/DB)                |
| Scalability      | Needs shared session store for multi-server  |
| Revocation       | Instant — delete session from store          |
| CSRF risk        | Yes — mitigated with SameSite + CSRF tokens  |

---

## 4. Cookie-Based Authentication

Cookies are the **transport mechanism** for sessions. But cookies can also store signed/encrypted data directly (stateless cookie auth).

### Cookie Attributes Explained

```
Set-Cookie: token=abc123;
            HttpOnly;        ← JS cannot access (prevents XSS theft)
            Secure;          ← HTTPS only
            SameSite=Lax;    ← Sent on same-site + top-level navigation
            Path=/;          ← Available for all routes
            Max-Age=3600;    ← Expire in 1 hour
            Domain=.app.com  ← Valid for app.com + subdomains
```

### SameSite Values

| Value  | Behavior                                              | CSRF Protection |
|--------|-------------------------------------------------------|-----------------|
| Strict | Cookie never sent on cross-site requests              | Strongest       |
| Lax    | Sent on top-level navigation (links), not XHR/forms   | Good            |
| None   | Always sent — must pair with Secure=true              | None            |

### Signed Cookie (Stateless) with FastAPI

```python
from fastapi import FastAPI, Response, Request, HTTPException
import hmac, hashlib, base64, json, time

app = FastAPI()
SECRET = b"super-secret-key"

def sign(data: dict) -> str:
    payload = base64.b64encode(json.dumps(data).encode()).decode()
    sig = hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"

def verify(cookie_value: str) -> dict:
    try:
        payload, sig = cookie_value.rsplit(".", 1)
        expected = hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("Invalid signature")
        data = json.loads(base64.b64decode(payload))
        if data["exp"] < time.time():
            raise ValueError("Expired")
        return data
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid cookie")

@app.post("/login")
def login(response: Response, username: str = "alice"):
    cookie = sign({"sub": username, "exp": time.time() + 3600})
    response.set_cookie("auth", cookie, httponly=True, secure=True, samesite="lax")
    return {"message": "Logged in"}

@app.get("/me")
def me(request: Request):
    cookie = request.cookies.get("auth")
    if not cookie:
        raise HTTPException(status_code=401)
    data = verify(cookie)
    return {"user": data["sub"]}
```

---

## 5. JWT Authentication

**JSON Web Token (JWT)** is a self-contained, signed token that encodes user data. No server-side state needed.

### JWT Structure

```
  HEADER          PAYLOAD              SIGNATURE
     │                │                    │
     ▼                ▼                    ▼
eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMSJ9.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
     └──────────────────────────────────────────┘
                  Base64URL encoded, NOT encrypted

Header:  { "alg": "HS256", "typ": "JWT" }
Payload: { "sub": "user1", "role": "admin", "exp": 1710000000 }
```

> **IMPORTANT**: JWT payload is Base64 encoded, NOT encrypted. Anyone can decode it. Never store secrets inside JWT.

### Standard JWT Claims

| Claim | Name       | Purpose                         |
|-------|------------|---------------------------------|
| `sub` | Subject    | User ID                         |
| `iss` | Issuer     | Who created the token           |
| `aud` | Audience   | Intended recipient              |
| `exp` | Expiry     | When the token expires (Unix)   |
| `iat` | Issued At  | When it was created             |
| `jti` | JWT ID     | Unique ID (for revocation)      |
| `nbf` | Not Before | Token not valid before this time|

---

### 5.1 Access Token

Short-lived token (5–15 min) used to access protected resources.

```
  CLIENT                          API SERVER
    │                               │
    │  POST /login {user, pass}     │
    │──────────────────────────────►│
    │◄──────────────────────────────│
    │  { access_token: "eyJ..." }   │
    │                               │
    │  GET /profile                 │
    │  Authorization: Bearer eyJ... │
    │──────────────────────────────►│
    │                               │  Verify signature
    │                               │  Check exp
    │                               │  Extract sub → user
    │◄──────────────────────────────│
    │  200 OK (profile data)        │
    │                               │
    │  GET /profile (token expired) │
    │──────────────────────────────►│
    │◄──────────────────────────────│
    │  401 Unauthorized             │
```

### FastAPI Access Token Implementation

```python
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta

app = FastAPI()

SECRET_KEY = "your-256-bit-secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# ─── Create token ─────────────────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + expires_delta
    payload["iat"] = datetime.utcnow()
    payload["type"] = "access"
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# ─── Verify token ─────────────────────────────────────────────────────────────
def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Wrong token type")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# ─── Login endpoint ───────────────────────────────────────────────────────────
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # In real app: verify against DB
    if form_data.username != "alice" or form_data.password != "secret":
        raise HTTPException(status_code=401, detail="Wrong credentials")

    access_token = create_access_token(
        data={"sub": form_data.username, "role": "admin"},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/profile")
def profile(user: dict = Depends(get_current_user)):
    return {"username": user["sub"], "role": user.get("role")}
```

---

### 5.2 Refresh Token

Long-lived token (7–30 days) used **only** to obtain a new access token when the old one expires. Stored securely (HttpOnly cookie or secure storage).

```
  CLIENT                      AUTH SERVER               RESOURCE SERVER
    │                               │                         │
    │  POST /login                  │                         │
    │──────────────────────────────►│                         │
    │◄──────────────────────────────│                         │
    │  access_token (15 min)        │                         │
    │  refresh_token (7 days)       │                         │
    │                               │                         │
    │  GET /data                    │                         │
    │  Authorization: Bearer <AT>   │                         │
    │──────────────────────────────────────────────────────►  │
    │◄──────────────────────────────────────────────────────  │
    │  200 OK                       │                         │
    │                               │                         │
    │  (15 min later, AT expired)   │                         │
    │                               │                         │
    │  GET /data                    │                         │
    │  Authorization: Bearer <AT>   │                         │
    │──────────────────────────────────────────────────────►  │
    │◄──────────────────────────────────────────────────────  │
    │  401 Unauthorized             │                         │
    │                               │                         │
    │  POST /refresh                │                         │
    │  { refresh_token: <RT> }      │                         │
    │──────────────────────────────►│                         │
    │                               │  Verify RT              │
    │                               │  Check not revoked      │
    │◄──────────────────────────────│                         │
    │  new access_token (15 min)    │                         │
    │                               │                         │
    │  GET /data (new AT)           │                         │
    │──────────────────────────────────────────────────────►  │
    │◄──────────────────────────────────────────────────────  │
    │  200 OK                       │                         │
```

### FastAPI Refresh Token Implementation

```python
from fastapi import FastAPI, Depends, HTTPException, Response, Request
from jose import JWTError, jwt
from datetime import datetime, timedelta
from redis import Redis

app = FastAPI()
redis = Redis(host="localhost", port=6379, decode_responses=True)

SECRET_KEY = "your-secret"
ALGORITHM = "HS256"

def create_token(data: dict, token_type: str, expires_delta: timedelta) -> str:
    payload = {
        **data,
        "type": token_type,
        "exp": datetime.utcnow() + expires_delta,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# ─── Login: issue both tokens ─────────────────────────────────────────────────
@app.post("/login")
def login(username: str, password: str, response: Response):
    # Verify credentials (simplified)
    if username != "alice" or password != "secret":
        raise HTTPException(status_code=401)

    access_token = create_token({"sub": username}, "access", timedelta(minutes=15))
    refresh_token = create_token({"sub": username}, "refresh", timedelta(days=7))

    # Store refresh token in Redis for revocation tracking
    redis.setex(f"refresh:{username}", 7 * 86400, refresh_token)

    # Refresh token goes in HttpOnly cookie
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=True)
    return {"access_token": access_token, "token_type": "bearer"}

# ─── Refresh endpoint ─────────────────────────────────────────────────────────
@app.post("/refresh")
def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Wrong token type")

        username = payload["sub"]

        # Verify token matches stored (not revoked)
        stored = redis.get(f"refresh:{username}")
        if stored != token:
            raise HTTPException(status_code=401, detail="Refresh token revoked")

        # Issue new access token
        new_access = create_token({"sub": username}, "access", timedelta(minutes=15))
        return {"access_token": new_access, "token_type": "bearer"}

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

# ─── Logout: revoke refresh token ─────────────────────────────────────────────
@app.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            redis.delete(f"refresh:{payload['sub']}")
        except JWTError:
            pass
    response.delete_cookie("refresh_token")
    return {"message": "Logged out"}
```

---

### 5.3 ID Token (OIDC)

Used in **OpenID Connect (OIDC)** — a layer on top of OAuth2 that adds identity. The ID token contains **who the user is** (profile info), not what they can access.

```
┌────────────────────────────────────────────────────────────────┐
│                    Token Comparison                            │
│                                                                │
│  Access Token   → "What you can DO"  (API permissions)        │
│  Refresh Token  → "Get new Access Token" (long-lived)         │
│  ID Token       → "Who you ARE"      (user identity/profile)  │
└────────────────────────────────────────────────────────────────┘

ID Token Payload Example:
{
  "sub": "user_123",
  "iss": "https://accounts.google.com",
  "aud": "my-client-id",
  "email": "alice@gmail.com",
  "name": "Alice Smith",
  "picture": "https://...",
  "email_verified": true,
  "exp": 1710000000
}
```

**OIDC Flow:**

```
  USER          CLIENT APP           GOOGLE (IdP)          YOUR API
   │                │                     │                    │
   │  Login w/ Google                     │                    │
   │───────────────►│                     │                    │
   │                │  Redirect to Google │                    │
   │                │────────────────────►│                    │
   │  Google login  │                     │                    │
   │◄───────────────────────────────────►│                    │
   │                │  Authorization Code │                    │
   │                │◄────────────────────│                    │
   │                │  Exchange code      │                    │
   │                │────────────────────►│                    │
   │                │◄────────────────────│                    │
   │                │  { access_token,    │                    │
   │                │    id_token,        │                    │
   │                │    refresh_token }  │                    │
   │                │                     │                    │
   │                │  GET /api/profile   │                    │
   │                │  Authorization: Bearer <access_token>   │
   │                │───────────────────────────────────────►│
   │                │◄───────────────────────────────────────│
```

---

### 5.4 Token Rotation

Refresh token rotation invalidates a refresh token after each use and issues a new one. Detects token reuse (theft).

```
  CLIENT                          AUTH SERVER
    │                               │
    │  POST /refresh {RT_v1}        │
    │──────────────────────────────►│
    │                               │  Validate RT_v1
    │                               │  Invalidate RT_v1
    │                               │  Issue AT_new + RT_v2
    │◄──────────────────────────────│
    │  { AT_new, RT_v2 }            │
    │                               │
    │ (Attacker also has RT_v1)     │
    │                               │
    │  POST /refresh {RT_v1}        │ ← Attacker reuses old token
    │──────────────────────────────►│
    │                               │  RT_v1 already used!
    │                               │  REVOKE ALL tokens for user
    │◄──────────────────────────────│
    │  401 — All sessions revoked   │
```

---

## 6. API Key Authentication

A static secret key issued to clients (typically for machine-to-machine or developer APIs). Sent via header or query param.

### Flow

```
  CLIENT (e.g., mobile app, service)       YOUR API
    │                                         │
    │  GET /data                              │
    │  X-API-Key: sk_live_abc123xyz           │
    │────────────────────────────────────────►│
    │                                         │  Lookup key in DB
    │                                         │  → belongs to "Company A"
    │                                         │  → has scope: read:data
    │◄────────────────────────────────────────│
    │  200 OK                                 │
```

### FastAPI API Key Implementation

```python
from fastapi import FastAPI, Security, HTTPException
from fastapi.security.api_key import APIKeyHeader, APIKeyQuery
import hashlib

app = FastAPI()

# Accept key from header OR query param
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)

# In production: store hashed keys in DB with associated metadata
VALID_KEYS = {
    hashlib.sha256(b"sk_live_abc123").hexdigest(): {"client": "app_A", "scopes": ["read"]},
    hashlib.sha256(b"sk_live_def456").hexdigest(): {"client": "app_B", "scopes": ["read", "write"]},
}

def get_api_key(
    header_key: str = Security(api_key_header),
    query_key: str = Security(api_key_query),
):
    raw_key = header_key or query_key
    if not raw_key:
        raise HTTPException(status_code=403, detail="API key required")

    hashed = hashlib.sha256(raw_key.encode()).hexdigest()
    key_data = VALID_KEYS.get(hashed)
    if not key_data:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return key_data

@app.get("/data")
def get_data(key_data: dict = Security(get_api_key)):
    if "read" not in key_data["scopes"]:
        raise HTTPException(status_code=403, detail="Insufficient scope")
    return {"data": "...", "accessed_by": key_data["client"]}
```

---

## 7. OAuth2

OAuth2 is an **authorization framework** — it lets a user grant a third-party app limited access to their account **without sharing their password**.

### OAuth2 Roles

```
┌─────────────────────────────────────────────────────────────────┐
│  Resource Owner  →  The user who owns data (you)               │
│  Client          →  The app requesting access (e.g., Spotify)  │
│  Auth Server     →  Issues tokens (e.g., Google)               │
│  Resource Server →  API that hosts the data (e.g., Google APIs)│
└─────────────────────────────────────────────────────────────────┘
```

### OAuth2 Flows

#### A. Authorization Code Flow (Most Secure — for Web Apps)

```
  USER            CLIENT APP           AUTH SERVER          RESOURCE SERVER
   │                  │                     │                     │
   │  Click "Login with Google"             │                     │
   │─────────────────►│                     │                     │
   │                  │  GET /authorize     │                     │
   │                  │  ?response_type=code│                     │
   │                  │  &client_id=...     │                     │
   │                  │  &redirect_uri=...  │                     │
   │                  │  &scope=read:email  │                     │
   │                  │  &state=random_csrf │                     │
   │                  │────────────────────►│                     │
   │  Login + Consent screen               │                     │
   │◄───────────────────────────────────────                     │
   │  Approve scope   │                     │                     │
   │─────────────────────────────────────►  │                     │
   │                  │  Redirect with code │                     │
   │                  │◄────────────────────│                     │
   │                  │  POST /token        │                     │
   │                  │  {code, client_secret, redirect_uri}     │
   │                  │────────────────────►│                     │
   │                  │◄────────────────────│                     │
   │                  │  { access_token,    │                     │
   │                  │    refresh_token,   │                     │
   │                  │    id_token }       │                     │
   │                  │                     │                     │
   │                  │  GET /userinfo      │                     │
   │                  │  Authorization: Bearer <AT>              │
   │                  │───────────────────────────────────────►  │
   │                  │◄───────────────────────────────────────  │
```

#### B. Client Credentials Flow (Machine to Machine)

```
  SERVICE A                   AUTH SERVER              SERVICE B (API)
    │                               │                       │
    │  POST /token                  │                       │
    │  { client_id,                 │                       │
    │    client_secret,             │                       │
    │    grant_type=client_credentials }                    │
    │──────────────────────────────►│                       │
    │◄──────────────────────────────│                       │
    │  { access_token }             │                       │
    │                               │                       │
    │  GET /api/resource            │                       │
    │  Authorization: Bearer <AT>   │                       │
    │──────────────────────────────────────────────────────►│
    │◄──────────────────────────────────────────────────────│
```

#### C. Device Code Flow (Smart TVs, CLIs)

```
  DEVICE / CLI                 AUTH SERVER            USER BROWSER
    │                               │                      │
    │  POST /device/authorize       │                      │
    │──────────────────────────────►│                      │
    │◄──────────────────────────────│                      │
    │  { device_code,               │                      │
    │    user_code: "ABCD-1234",    │                      │
    │    verification_uri }         │                      │
    │                               │                      │
    │  Display: "Go to example.com  │                      │
    │            enter ABCD-1234"   │                      │
    │                               │                      │
    │  Poll POST /token             │                      │
    │  (every 5 seconds)            │   User opens browser │
    │──────────────────────────────►│◄────────────────────►│
    │◄──────────────────────────────│  User enters code    │
    │  { pending... }               │  + approves          │
    │                               │                      │
    │  Poll POST /token             │                      │
    │──────────────────────────────►│                      │
    │◄──────────────────────────────│                      │
    │  { access_token }  ✓          │                      │
```

### FastAPI OAuth2 with Password Flow (simplified)

```python
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt
from datetime import datetime, timedelta

app = FastAPI()
SECRET = "secret"
ALGORITHM = "HS256"

fake_users = {
    "alice": {"hashed_password": "fakehashedsecret", "role": "admin"},
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

@app.post("/token")
def issue_token(form: OAuth2PasswordRequestForm = Depends()):
    user = fake_users.get(form.username)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    token = jwt.encode(
        {"sub": form.username, "role": user["role"],
         "exp": datetime.utcnow() + timedelta(minutes=30)},
        SECRET, algorithm=ALGORITHM
    )
    return {"access_token": token, "token_type": "bearer"}

def get_user(token: str = Depends(oauth2_scheme)):
    try:
        return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/me")
def me(user=Depends(get_user)):
    return user
```

---

## 8. Role-Based Access Control (RBAC)

Authorization via roles. Users have roles → roles have permissions.

```
  USER ──── has role ────► ROLE ──── has permission ────► RESOURCE
  alice       admin         admin        delete               /users
  bob         viewer        viewer       read                 /reports
```

### FastAPI RBAC Implementation

```python
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from functools import wraps
from typing import List

app = FastAPI()
SECRET = "secret"
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

# ─── Permission map ───────────────────────────────────────────────────────────
ROLE_PERMISSIONS = {
    "admin":  ["read", "write", "delete"],
    "editor": ["read", "write"],
    "viewer": ["read"],
}

# ─── Dependency: decode token ─────────────────────────────────────────────────
def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    try:
        return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

# ─── Permission checker factory ───────────────────────────────────────────────
def require_permission(permission: str):
    def checker(user: dict = Depends(get_current_user)):
        role = user.get("role", "viewer")
        allowed = ROLE_PERMISSIONS.get(role, [])
        if permission not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role}' cannot perform '{permission}'"
            )
        return user
    return checker

# ─── Routes with authorization ────────────────────────────────────────────────
@app.get("/reports")
def read_reports(user=Depends(require_permission("read"))):
    return {"reports": [...]}

@app.post("/reports")
def create_report(user=Depends(require_permission("write"))):
    return {"created": True}

@app.delete("/reports/{id}")
def delete_report(id: int, user=Depends(require_permission("delete"))):
    return {"deleted": id}
```

---

## 9. Scenario Reference Table

| Scenario                          | Best Strategy                                        | Why                                                          |
|-----------------------------------|------------------------------------------------------|--------------------------------------------------------------|
| Traditional web app (MPA)         | Session + HttpOnly Cookie                            | Server controls state, easy revocation                      |
| SPA (React, Vue) + REST API       | JWT Access Token (memory) + Refresh Token (cookie)  | Stateless API, refresh token safe from XSS                  |
| Mobile app                        | JWT Access + Refresh Token (secure storage)          | No cookies, secure device storage available                  |
| Microservices (internal)          | JWT passed between services                          | Services verify signature without shared session store       |
| Machine to Machine (M2M)          | OAuth2 Client Credentials or API Key                 | No user involved, service identity                           |
| Third-party integrations          | OAuth2 Authorization Code                            | User grants limited access without sharing password          |
| CLI tools / IoT / Smart TVs       | OAuth2 Device Code Flow                              | No browser available on the device                           |
| Public API (developer access)     | API Key (hashed in DB)                               | Simple, scoped, easily revocable per key                     |
| Admin panel (high security)       | Session + MFA + short timeout                        | Human-facing, sensitive, needs strong revocation             |
| SSO (enterprise login)            | OIDC / SAML                                          | Centralized identity across multiple services                |
| Passwordless login                | Magic link (email) or OTP (SMS)                      | Removes password attack surface                              |
| "Login with Google/GitHub"        | OAuth2 Authorization Code + OIDC                     | Use existing identity provider                               |

---

## 10. Security Best Practices

### Token Storage

```
┌──────────────────────────────────────────────────────────────────┐
│  WHERE TO STORE TOKENS                                           │
│                                                                  │
│  Access Token  →  Memory (JS variable / React state)            │
│                   ✓ Safe from XSS (not persisted)               │
│                   ✗ Lost on refresh (use refresh token to renew) │
│                                                                  │
│  Refresh Token →  HttpOnly Cookie                               │
│                   ✓ Inaccessible to JS (XSS-safe)              │
│                   ✓ Auto-sent by browser                        │
│                   ✓ SameSite prevents CSRF                      │
│                                                                  │
│  NEVER store tokens in:                                          │
│  ✗ localStorage  (vulnerable to XSS)                            │
│  ✗ sessionStorage (same as localStorage)                        │
│  ✗ Regular cookies without HttpOnly                             │
└──────────────────────────────────────────────────────────────────┘
```

### Password Hashing

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

### HTTPS, CORS, Rate Limiting

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address

app = FastAPI()
limiter = Limiter(key_func=get_remote_address)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # Never use "*" with credentials
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/login")
@limiter.limit("5/minute")  # Prevent brute force
def login(request: Request):
    ...
```

### Quick Security Checklist

| Item                                        | Done? |
|---------------------------------------------|-------|
| Passwords hashed with bcrypt/argon2         | ☐     |
| JWTs signed (HS256/RS256), never plain      | ☐     |
| Short-lived access tokens (< 15 min)        | ☐     |
| Refresh tokens in HttpOnly cookies          | ☐     |
| HTTPS enforced everywhere                   | ☐     |
| CORS restricted to known origins            | ☐     |
| Rate limiting on login/refresh endpoints    | ☐     |
| API keys stored as hashes, never plaintext  | ☐     |
| JWT `exp`, `iss`, `aud` claims validated    | ☐     |
| Refresh token rotation enabled              | ☐     |
| Logout deletes/revokes server-side state    | ☐     |
| Input validated (no SQL/command injection)  | ☐     |

---

*Generated: 2026-03-12 | FastAPI version reference: 0.110+*
