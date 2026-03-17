# gitDeploy — Frontend Specification

> **For the UI developer.**
> Everything in this document is derived directly from the actual backend code — schemas, validators, response shapes, cookie behaviour.
> Design reference: [Vercel Dashboard](https://vercel.com/dashboard)
> Last updated: 2026-03-12

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [Folder Structure](#3-folder-structure)
4. [Environment Variables](#4-environment-variables)
5. [API Reference — Exact Contracts](#5-api-reference--exact-contracts)
6. [Auth Flow (in full detail)](#6-auth-flow-in-full-detail)
7. [Axios Setup](#7-axios-setup)
8. [Pages & Routes](#8-pages--routes)
9. [Forms — Every Field, Label, Validation](#9-forms--every-field-label-validation)
10. [UI States to Handle](#10-ui-states-to-handle)
11. [Design Tokens](#11-design-tokens)
12. [Docker Setup](#12-docker-setup)

---

## 1. Project Overview

**gitDeploy** is a self-hosted platform where users deploy any public GitHub repository as a Docker container with an auto-assigned subdomain — like a self-hosted Vercel.

```
User links a GitHub repo
    └── Provide: repo URL, port, branch, Dockerfile path
App is deployed
    └── Backend: clones repo → docker build → docker run → assigns port
App goes live
    └── Accessible at: app-{id}.yourdomain.com  (via Traefik)
```

**User can:**
- Register / Login / Logout
- Create an app (link a GitHub repo)
- Deploy / Redeploy an app (with config overrides per deploy)
- View app status, details, env vars
- Delete an app

---

## 2. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Framework | React 18 + Vite | Fast dev server, ESM build |
| Language | TypeScript | Strict mode on |
| Routing | React Router v6 | Nested routes |
| HTTP | Axios | With interceptor for auto-refresh |
| State | Zustand | Auth store + app store |
| Styling | Tailwind CSS v3 | Dark-first, like Vercel |
| Forms | React Hook Form | + Zod for schema validation |
| Icons | Lucide React | Consistent icon set |
| Notifications | react-hot-toast | Minimal toasts |

---

## 3. Folder Structure

```
frontend/
├── public/
│   └── favicon.svg
├── src/
│   ├── api/
│   │   ├── axiosInstance.ts      ← Axios config + interceptors (DO NOT skip)
│   │   ├── auth.api.ts           ← login / register / refresh / logout / me
│   │   └── apps.api.ts           ← create / list / get / deploy / delete
│   │
│   ├── store/
│   │   ├── auth.store.ts         ← accessToken (memory), user object
│   │   └── apps.store.ts         ← apps list cache
│   │
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── SignupPage.tsx
│   │   ├── DashboardPage.tsx
│   │   ├── NewAppPage.tsx
│   │   ├── AppDetailPage.tsx
│   │   └── NotFoundPage.tsx
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppShell.tsx      ← sidebar + topbar wrapper
│   │   │   ├── Sidebar.tsx
│   │   │   └── TopBar.tsx
│   │   ├── apps/
│   │   │   ├── AppCard.tsx       ← used on dashboard grid
│   │   │   ├── AppStatusBadge.tsx
│   │   │   └── EnvVarEditor.tsx  ← key/value pair editor
│   │   └── ui/
│   │       ├── Button.tsx
│   │       ├── Input.tsx
│   │       ├── Label.tsx
│   │       ├── Card.tsx
│   │       └── Spinner.tsx
│   │
│   ├── hooks/
│   │   ├── useAuth.ts            ← login/logout/register helpers
│   │   └── useApps.ts            ← CRUD helpers wrapping api calls
│   │
│   ├── router/
│   │   ├── index.tsx             ← Route definitions
│   │   └── ProtectedRoute.tsx    ← Redirects to /login if not authed
│   │
│   ├── types/
│   │   ├── auth.types.ts
│   │   └── app.types.ts
│   │
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
│
├── .env.example
├── .env.local                    ← gitignored
├── Dockerfile.frontend
├── nginx.conf                    ← SPA fallback config (inside container)
├── index.html
├── vite.config.ts
├── tailwind.config.ts
└── tsconfig.json
```

---

## 4. Environment Variables

```bash
# .env.example
VITE_API_BASE_URL=http://localhost:8000
# In production: https://api.yourdomain.com
```

> Only `VITE_` prefixed vars are exposed to the browser by Vite.

---

## 5. API Reference — Exact Contracts

All endpoints are prefixed with `/api/v1`.
All authenticated endpoints require: `Authorization: Bearer <access_token>`

---

### Auth Endpoints

#### `POST /api/v1/auth/register`

**Request body:**
```ts
{
  username: string   // min 3, max 50 chars, only letters/numbers/underscores
  email: string      // valid email, stored lowercase
  password: string   // min 8 chars
}
```

**201 Response:**
```ts
{
  id: number
  username: string
  email: string
  role: "user" | "admin"
  billing_type: "free" | "paid"
}
```

**Error cases:**
| Status | When |
|--------|------|
| 409 | `"Email already registered"` or `"Username already registered"` |
| 422 | Validation failed (email format, username chars, password length) |

---

#### `POST /api/v1/auth/login`

**Request body:**
```ts
{
  email: string
  password: string
}
```

**200 Response (body):**
```ts
{
  access_token: string   // JWT, valid 15 minutes
  token_type: "bearer"
}
```

**200 Response (cookie):**
```
Set-Cookie: refresh_token=<jwt>;
            HttpOnly; SameSite=Lax;
            Path=/api/v1/auth/refresh;   ← IMPORTANT: scoped to refresh path only
            Max-Age=604800               ← 7 days
```

> ⚠️ The refresh cookie is **path-scoped to `/api/v1/auth/refresh`**. The browser will only send it on requests to that exact path. Axios `withCredentials: true` must be set.

**Error cases:**
| Status | When |
|--------|------|
| 401 | Wrong email or password |

---

#### `POST /api/v1/auth/refresh`

No request body. The browser sends the `refresh_token` cookie automatically.

**200 Response:**
```ts
{
  access_token: string   // New JWT, valid 15 minutes
  token_type: "bearer"
}
```

**Error cases:**
| Status | When |
|--------|------|
| 401 | Cookie missing, token expired, token invalid, user not found |

---

#### `POST /api/v1/auth/logout`

No request body.

**200 Response:**
```ts
{ message: "Logged out successfully" }
```
> Backend deletes the `refresh_token` cookie. Frontend should also clear the in-memory access token.

---

#### `GET /api/v1/auth/me`  🔒 Requires auth

**200 Response:**
```ts
{
  id: number
  username: string
  email: string
  role: "user" | "admin"
  billing_type: "free" | "paid"
}
```

---

### Apps Endpoints

#### `POST /api/v1/apps/create`  🔒 Requires auth

**Request body:**
```ts
{
  name: string          // min 3, max 255 chars
  repo_url: string      // must be a valid public GitHub URL
  container_port: number // port your app listens on inside the container
  branch?: string       // default: "main"
  source_dir?: string   // default: "."
  dockerfile_path?: string  // default: "Dockerfile"
  env?: Record<string, string>  // default: {}
}
```

**201 Response:**
```ts
{
  id: number
  subdomain: string     // "app-{id}" — e.g. "app-42"
  container_port: number
  status: "created"     // always "created" on first create
}
```

**Error cases:**
| Status | When |
|--------|------|
| 400 | Invalid GitHub URL format |
| 404 | GitHub repo not found or is private |
| 422 | Validation error (name too short, missing required fields) |

---

#### `GET /api/v1/apps/list/`  🔒 Requires auth

**Query params:**
```
?status=running    optional — one of: created | running | error | prepared
&page=1            optional — default 1
&size=20           optional — default 20
```

**200 Response:**
```ts
Array<{
  id: number
  name: string
  subdomain: string     // "app-{id}"
  container_port: number
  repo_url: string
  build_path: string    // source_dir value
  branch: string
  status: "created" | "running" | "error" | "prepared"
}>
```

---

#### `GET /api/v1/apps/{app_id}`  🔒 Requires auth

**200 Response:**
```ts
{
  id: number
  name: string
  repo_url: string
  subdomain: string
  internal_port: number | null   // null until first deploy
  container_port: number
  branch: string
  build_path: string
  dockerfile_path: string
  status: "created" | "running" | "error" | "prepared"
  created_at: string             // ISO 8601 datetime
  updated_at: string             // ISO 8601 datetime
  env: Record<string, string>
}
```

**Error cases:**
| Status | When |
|--------|------|
| 403 | App belongs to another user |
| 404 | App not found |

---

#### `DELETE /api/v1/apps/delete/{app_id}`  🔒 Requires auth

**204 Response** — No body.

> Removes container, image, cloned repo files, log files, and DB record.

---

#### `POST /api/v1/apps/{app_id}/deploy`  🔒 Requires auth

All fields are optional. Provided values override what was saved at create time for this deploy only.

**Request body:**
```ts
{
  branch?: string            // override branch for this deploy
  source_dir?: string        // override source directory
  dockerfile_path?: string   // override Dockerfile location
  env?: Record<string, string>  // override env vars
  force_rebuild?: boolean    // delete cloned repo and clone fresh (default false)
  build_args?: Record<string, string>  // Docker build-time ARGs
  clear_cache?: boolean      // pass --no-cache to docker build (default false)
}
```

**201 Response:**
```ts
{
  id: number
  status: "running" | "error"
}
```

**Error cases:**
| Status | When |
|--------|------|
| 403 | App belongs to another user |
| 404 | App not found |
| 500 | Docker build failed, Docker run failed |

> ⚠️ Deploy is **synchronous** — the request takes time (git clone + docker build). Show a loading state. Do not timeout early.

---

## 6. Auth Flow (in full detail)

### On App Load

```
App starts
    │
    ├── accessToken in memory? ─── Yes ──► load normally
    │
    └── No
         │
         └── POST /api/v1/auth/refresh
              │
              ├── 200 ──► store new accessToken → load normally
              │
              └── 401 ──► redirect to /login
```

### Login Flow

```
User submits /login form
    │
    └── POST /api/v1/auth/login { email, password }
         │
         ├── 200 ──► store access_token in memory (Zustand, NOT localStorage)
         │           cookie is set automatically by browser
         │           GET /api/v1/auth/me → store user in Zustand
         │           redirect to /dashboard
         │
         └── 401 ──► show "Invalid email or password" under form
```

### Every API call

```
Axios request interceptor
    └── reads accessToken from Zustand store
        └── sets Authorization: Bearer <token>
```

### Token expires mid-session (auto-refresh)

```
Any API call returns 401
    │
    └── Axios response interceptor
         │
         └── POST /api/v1/auth/refresh  (cookie sent automatically)
              │
              ├── 200 ──► update accessToken in store
              │           retry original request with new token
              │
              └── 401 ──► clear store → redirect to /login
```

### Logout

```
User clicks logout
    │
    └── POST /api/v1/auth/logout
         └── clear accessToken and user from Zustand store
             redirect to /login
```

---

## 7. Axios Setup

```ts
// src/api/axiosInstance.ts
import axios from 'axios';
import { useAuthStore } from '../store/auth.store';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  withCredentials: true,   // sends refresh_token cookie on /api/v1/auth/refresh
});

// ── Attach access token to every request ─────────────────────────────────────
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Auto-refresh on 401 ───────────────────────────────────────────────────────
let isRefreshing = false;
let queue: Array<(token: string) => void> = [];

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;

    // Don't retry the refresh call itself
    if (original.url?.includes('/auth/refresh')) {
      useAuthStore.getState().clearAuth();
      window.location.href = '/login';
      return Promise.reject(error);
    }

    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;

      if (isRefreshing) {
        // Queue requests that come in while refresh is in flight
        return new Promise((resolve) => {
          queue.push((token) => {
            original.headers.Authorization = `Bearer ${token}`;
            resolve(api(original));
          });
        });
      }

      isRefreshing = true;

      try {
        const { data } = await api.post('/api/v1/auth/refresh');
        const newToken = data.access_token;
        useAuthStore.getState().setAccessToken(newToken);
        queue.forEach((cb) => cb(newToken));
        queue = [];
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      } catch {
        useAuthStore.getState().clearAuth();
        window.location.href = '/login';
        return Promise.reject(error);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);
```

```ts
// src/store/auth.store.ts
import { create } from 'zustand';

interface User {
  id: number;
  username: string;
  email: string;
  role: 'user' | 'admin';
  billing_type: 'free' | 'paid';
}

interface AuthStore {
  accessToken: string | null;
  user: User | null;
  setAccessToken: (token: string) => void;
  setUser: (user: User) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
  accessToken: null,
  user: null,
  setAccessToken: (token) => set({ accessToken: token }),
  setUser: (user) => set({ user }),
  clearAuth: () => set({ accessToken: null, user: null }),
}));
```

---

## 8. Pages & Routes

```
/                   → redirect to /dashboard (if authed) or /login
/login              → LoginPage        (public)
/signup             → SignupPage       (public)
/dashboard          → DashboardPage    🔒
/apps/new           → NewAppPage       🔒
/apps/:id           → AppDetailPage    🔒
*                   → NotFoundPage
```

### Route Setup

```tsx
// src/router/index.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import ProtectedRoute from './ProtectedRoute';

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/apps/new" element={<NewAppPage />} />
            <Route path="/apps/:id" element={<AppDetailPage />} />
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
}
```

```tsx
// src/router/ProtectedRoute.tsx
import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '../store/auth.store';

export default function ProtectedRoute() {
  const { accessToken } = useAuthStore();
  if (!accessToken) return <Navigate to="/login" replace />;
  return <Outlet />;
}
```

---

## 9. Forms — Every Field, Label, Validation

All validation rules come directly from the backend schemas and `field_validator` logic.

---

### Form 1 — Sign Up

**Route:** `/signup` → `POST /api/v1/auth/register`

| Field | Label | Type | Placeholder | Rules |
|-------|-------|------|-------------|-------|
| `username` | Username | text | `alice` | Required · min 3 · max 50 · only `a-z A-Z 0-9 _` |
| `email` | Email address | email | `alice@example.com` | Required · valid email format |
| `password` | Password | password | `••••••••` | Required · min 8 chars |
| `confirmPassword` | Confirm password | password | `••••••••` | Must match `password` (client-side only) |

**Submit button:** `Create account`

**After success:** Show toast "Account created!" → redirect to `/login`

**Error handling:**
```
409 with "Email already registered"    → show under email field
409 with "Username already registered" → show under username field
422                                    → show field-level Zod errors
```

**Link below form:** Already have an account? [Log in] → `/login`

---

### Form 2 — Log In

**Route:** `/login` → `POST /api/v1/auth/login`

| Field | Label | Type | Placeholder | Rules |
|-------|-------|------|-------------|-------|
| `email` | Email address | email | `alice@example.com` | Required |
| `password` | Password | password | `••••••••` | Required |

**Submit button:** `Log in`

**After success:** `GET /api/v1/auth/me` → store user → redirect to `/dashboard`

**Error handling:**
```
401 → show banner "Invalid email or password" (do NOT say which one is wrong)
```

**Link below form:** Don't have an account? [Sign up] → `/signup`

---

### Form 3 — Create App

**Route:** `/apps/new` → `POST /api/v1/apps/create`

#### Section 1 — Basic Info

| Field | Label | Type | Placeholder | Default | Rules |
|-------|-------|------|-------------|---------|-------|
| `name` | App name | text | `my-web-app` | — | Required · min 3 · max 255 |
| `repo_url` | GitHub repository URL | url | `https://github.com/user/repo` | — | Required · must start with `https://github.com/` |

#### Section 2 — Build Config

| Field | Label | Type | Placeholder | Default | Rules |
|-------|-------|------|-------------|---------|-------|
| `container_port` | Container port | number | `8000` | — | Required · integer · 1–65535 |
| `branch` | Branch | text | `main` | `main` | Optional |
| `source_dir` | Source directory | text | `.` | `.` | Optional |
| `dockerfile_path` | Dockerfile path | text | `Dockerfile` | `Dockerfile` | Optional |

#### Section 3 — Environment Variables

Dynamic key-value editor (add/remove rows):

| Sub-field | Label | Type | Placeholder |
|-----------|-------|------|-------------|
| key | Key | text | `DATABASE_URL` |
| value | Value | text | `postgres://...` |

**Add row button:** `+ Add variable`

**Submit button:** `Create app`

**After success:**
- Show toast `"App created successfully"`
- Redirect to `/apps/{id}` (use the `id` from the response)

---

### Form 4 — Deploy App

**Location:** Inside `/apps/:id` page, in a "Deploy" panel
**Endpoint:** `POST /api/v1/apps/{app_id}/deploy`

> All fields are **optional overrides** for this deploy. Show current saved values as placeholders.

| Field | Label | Type | Placeholder | Default |
|-------|-------|------|-------------|---------|
| `branch` | Branch | text | *(current app branch)* | leave blank = no change |
| `source_dir` | Source directory | text | *(current source_dir)* | leave blank = no change |
| `dockerfile_path` | Dockerfile path | text | *(current dockerfile_path)* | leave blank = no change |

#### Deploy Options (collapsible "Advanced" section)

| Field | Label | Type | Default | Notes |
|-------|-------|------|---------|-------|
| `force_rebuild` | Force fresh clone | checkbox | `false` | Deletes cloned repo, re-clones from scratch |
| `clear_cache` | Disable Docker build cache | checkbox | `false` | Passes `--no-cache` to `docker build` |
| `build_args` | Build arguments | key-value editor | `{}` | Docker build-time `ARG` values |
| `env` | Environment variable overrides | key-value editor | `{}` | Overrides env for this deploy |

**Submit button:** `Deploy`

**Loading state:** Button shows `Deploying…` spinner. Disable all fields. Keep loading until response (deploy is synchronous — may take 30–120 seconds).

**After success:**
- Show toast `"Deployment successful"` (green)
- Refresh app status badge to `running`

**After error (500):**
- Show toast `"Deployment failed"` (red)
- Refresh app status badge to `error`

---

## 10. UI States to Handle

### App Status Badge

Map the `status` string to a badge:

| Value | Label | Colour |
|-------|-------|--------|
| `created` | Created | Grey |
| `prepared` | Preparing | Blue |
| `running` | Running | Green |
| `error` | Error | Red |

### Dashboard — App Card

Show for each app in `/api/v1/apps/list/`:

```
┌─────────────────────────────────────────────┐
│  ● Running          my-web-app              │
│                                             │
│  github.com/user/repo  ·  main              │
│  app-42.yourdomain.com                      │
│                                   [Deploy]  │
└─────────────────────────────────────────────┘
```

Fields to display: `name`, `status` badge, `repo_url` (short), `branch`, `subdomain` as link.

### App Detail Page (`/apps/:id`)

Two-column layout:

**Left column — Info panel:**
```
Name:           my-web-app
Status:         ● Running
Subdomain:      app-42.yourdomain.com  ↗
Repository:     github.com/user/repo   ↗
Branch:         main
Container port: 8000
Internal port:  10042  (null until deployed)
Source dir:     .
Dockerfile:     Dockerfile
Created:        12 Mar 2026, 14:32
Last updated:   12 Mar 2026, 15:01
```

**Right column — Deploy panel:**
Deploy form (Form 4 above) + Danger zone with Delete button.

### Delete Confirmation Modal

Before calling `DELETE /api/v1/apps/delete/{id}`:
```
Are you sure you want to delete "my-web-app"?
This will stop the container, remove all files, and cannot be undone.

[Cancel]  [Delete app]
```

### Empty Dashboard State

When `GET /api/v1/apps/list/` returns `[]`:

```
        🚀
   No apps yet
   Deploy your first GitHub repo in seconds.

        [Create your first app]
```

### Error State (API down / network error)

```
  ⚠ Something went wrong
  Unable to reach the server. Check your connection.
  [Retry]
```

### Full-page loader (on app boot — checking session)

Show a centred spinner while calling `POST /api/v1/auth/refresh` on startup. Replace once resolved.

---

## 11. Design Tokens

```ts
// tailwind.config.ts — extend with these
colors: {
  background:  '#0a0a0a',   // near-black page bg (Vercel-style)
  surface:     '#111111',   // cards, inputs
  border:      '#1f1f1f',   // subtle borders
  muted:       '#888888',   // secondary text
  accent:      '#ffffff',   // primary text, active items
  success:     '#22c55e',   // running badge
  danger:      '#ef4444',   // error badge, delete button
  warning:     '#f59e0b',   // prepared badge
  info:        '#3b82f6',   // created badge, links
}
fontFamily: {
  sans: ['Inter', 'system-ui', 'sans-serif'],
  mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
}
```

---

## 12. Docker Setup

### `Dockerfile.frontend`

```dockerfile
# ── Stage 1: build ─────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Inject API URL at build time
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build
# Output is in /app/dist

# ── Stage 2: serve ─────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# SPA fallback — all unknown paths serve index.html (React Router handles them)
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
```

---

### `nginx.conf` (inside container — serves the built React app)

> This is NOT a reverse proxy. It only serves static files and handles SPA routing.

```nginx
server {
    listen 3000;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # React Router — send all non-file requests to index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location ~* \.(js|css|png|svg|ico|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/javascript application/json image/svg+xml;
}
```

---

### How it fits in `docker-compose.yml` (backend already has this)

```yaml
frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile.frontend
    args:
      VITE_API_BASE_URL: https://api.yourdomain.com
  container_name: gitdeploy-frontend
  restart: unless-stopped
  networks:
    - web
  labels:
    - "traefik.enable=true"
    - "traefik.http.routers.frontend.rule=Host(`yourdomain.com`) || Host(`www.yourdomain.com`)"
    - "traefik.http.services.frontend.loadbalancer.server.port=3000"
```

> Traefik handles public routing. Nginx inside the container only does SPA fallback + static file serving. No port is exposed to the host.

---

### `vite.config.ts` (dev server proxy — avoids CORS in local dev)

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // cookies are forwarded — refresh flow works in dev
      },
    },
  },
});
```

> In local dev, point `VITE_API_BASE_URL` to `''` (empty) so all `/api/*` calls go through the Vite proxy.

---

*gitDeploy Frontend Spec — generated 2026-03-12*
*Based on: api/v1/auth.py · api/v1/apps.py · app/schemas/ · app/constants.py*
