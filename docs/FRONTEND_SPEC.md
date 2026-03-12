# gitDeploy — Frontend UI Specification

> **For the UI developer.** This document is the single source of truth for building the React frontend.
> Design reference: [Vercel Dashboard](https://vercel.com/dashboard)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [Project Folder Structure](#3-project-folder-structure)
4. [Design System & Tokens](#4-design-system--tokens)
5. [Pages & Routes](#5-pages--routes)
   - [Auth Pages](#auth-pages)
   - [Dashboard](#dashboard)
   - [Apps](#apps)
   - [Deploy](#deploy)
   - [Settings](#settings)
6. [Forms — Complete Field Reference](#6-forms--complete-field-reference)
7. [API Integration](#7-api-integration)
8. [Auth Flow (Frontend)](#8-auth-flow-frontend)
9. [Docker Setup](#9-docker-setup)
10. [Nginx Configuration](#10-nginx-configuration)
11. [Environment Variables](#11-environment-variables)

---

## 1. Project Overview

**gitDeploy** is a self-hosted deployment platform that lets users deploy any public GitHub repository as a Docker container with automatic port allocation and subdomain routing — similar to Vercel but self-hosted.

```
User creates an App
    └── Provides GitHub repo URL + config
App is Deployed
    └── Backend: clones repo → builds Docker image → runs container
App goes Live
    └── Accessible at: app-{id}.yourdomain.com
```

**Core user actions:**
- Register / Login
- Create an app (link a GitHub repo)
- Deploy / Redeploy an app (with optional config overrides)
- Monitor app status (running / error / created)
- Delete an app

---

## 2. Tech Stack

| Layer            | Technology                                                                  |
|------------------|-----------------------------------------------------------------------------|
| Framework        | React 18 + Vite                                                             |
| Language         | TypeScript                                                                  |
| Routing          | React Router v6                                                             |
| State Management | Zustand (lightweight, no boilerplate)                                       |
| Server State     | TanStack Query (React Query v5) — API calls, caching, loading states        |
| Forms            | React Hook Form + Zod (validation)                                          |
| Styling          | Tailwind CSS v3 + shadcn/ui (component primitives)                          |
| Icons            | Lucide React                                                                |
| HTTP Client      | Axios (with interceptors for auth)                                          |
| Notifications    | sonner (toast library)                                                      |
| Code Editor      | Monaco Editor (for env var editing)                                         |
| Linting          | ESLint + Prettier                                                           |

### Install Commands

```bash
npm create vite@latest gitdeploy-ui -- --template react-ts
cd gitdeploy-ui

npm install react-router-dom @tanstack/react-query zustand
npm install react-hook-form @hookform/resolvers zod
npm install axios sonner lucide-react
npm install @monaco-editor/react

# shadcn/ui setup
npx shadcn-ui@latest init

# Tailwind
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

---

## 3. Project Folder Structure

```
gitdeploy-ui/
├── public/
│   └── favicon.ico
├── src/
│   ├── api/                    # Axios instances + API call functions
│   │   ├── client.ts           # Axios config, interceptors, token refresh
│   │   ├── auth.ts             # login, register, logout, refresh
│   │   └── apps.ts             # createApp, listApps, getApp, deployApp, deleteApp
│   │
│   ├── components/             # Reusable UI components
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── Topbar.tsx
│   │   │   └── AppShell.tsx    # Sidebar + Topbar wrapper
│   │   ├── ui/                 # shadcn/ui primitives (auto-generated)
│   │   ├── AppCard.tsx
│   │   ├── StatusBadge.tsx
│   │   ├── DeployButton.tsx
│   │   └── EmptyState.tsx
│   │
│   ├── pages/                  # One file per route
│   │   ├── auth/
│   │   │   ├── LoginPage.tsx
│   │   │   └── RegisterPage.tsx
│   │   ├── DashboardPage.tsx
│   │   ├── AppsListPage.tsx
│   │   ├── AppDetailPage.tsx
│   │   ├── NewAppPage.tsx
│   │   ├── DeployPage.tsx
│   │   └── SettingsPage.tsx
│   │
│   ├── hooks/                  # Custom React hooks
│   │   ├── useAuth.ts
│   │   ├── useApps.ts
│   │   └── useDeployment.ts
│   │
│   ├── store/                  # Zustand stores
│   │   └── authStore.ts        # user, accessToken, setToken, clear
│   │
│   ├── types/                  # TypeScript interfaces
│   │   ├── app.ts
│   │   └── auth.ts
│   │
│   ├── lib/
│   │   └── utils.ts            # cn() helper, formatDate, etc.
│   │
│   ├── router/
│   │   └── index.tsx           # All routes + ProtectedRoute wrapper
│   │
│   ├── App.tsx
│   └── main.tsx
│
├── Dockerfile
├── nginx.conf                  # Nginx config for serving React build
├── docker-compose.yml
├── .env.example
├── .env.development
├── .env.production
├── vite.config.ts
├── tailwind.config.ts
└── tsconfig.json
```

---

## 4. Design System & Tokens

Reference design: Vercel dashboard — dark-first, minimal, monospace for code values.

### Color Palette (Tailwind config)

```ts
// tailwind.config.ts
export default {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background:  "#0a0a0a",   // Page background
        surface:     "#111111",   // Card / sidebar background
        border:      "#1f1f1f",   // Dividers, input borders
        muted:       "#888888",   // Placeholder, secondary text
        foreground:  "#ededed",   // Primary text
        primary:     "#ffffff",   // Buttons, active states
        accent:      "#0070f3",   // Links, focus rings (Vercel blue)
        success:     "#50e3c2",   // Running status
        warning:     "#f5a623",   // Prepared status
        error:       "#ff4444",   // Error status
        created:     "#888888",   // Created (not deployed) status
      },
      fontFamily: {
        sans: ["Geist Sans", "Inter", "system-ui", "sans-serif"],
        mono: ["Geist Mono", "JetBrains Mono", "monospace"],
      },
    },
  },
}
```

### Status Badge Colors

| Status      | Color      | Label       |
|-------------|------------|-------------|
| `created`   | gray       | Created     |
| `running`   | teal/green | Running     |
| `error`     | red        | Error       |
| `prepared`  | yellow     | Prepared    |

### Typography Scale

```
Page title:     text-2xl font-semibold
Section header: text-sm font-medium text-muted uppercase tracking-wider
Body:           text-sm text-foreground
Muted:          text-sm text-muted
Code/URL:       font-mono text-xs
Label (form):   text-sm font-medium
```

---

## 5. Pages & Routes

```
/login                → LoginPage        (public)
/register             → RegisterPage     (public)
/                     → DashboardPage    (protected)
/apps                 → AppsListPage     (protected)
/apps/new             → NewAppPage       (protected)
/apps/:id             → AppDetailPage    (protected)
/apps/:id/deploy      → DeployPage       (protected)
/settings             → SettingsPage     (protected)
```

### Protected Route Wrapper

```tsx
// router/index.tsx
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { accessToken } = useAuthStore();
  if (!accessToken) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
```

---

### Auth Pages

---

#### `/login` — Login Page

**Purpose:** Authenticate existing user, receive access + refresh tokens.

**Layout:** Centered card (max-w-sm), logo top, form, link to register.

```
┌─────────────────────────────────┐
│          gitDeploy              │  ← logo / wordmark
│                                 │
│  Sign in to your account        │  ← heading
│                                 │
│  Email                          │
│  [________________________]     │
│                                 │
│  Password                       │
│  [________________________] 👁  │
│                                 │
│  [       Sign In        ]       │  ← primary button, full width
│                                 │
│  Don't have an account? Register│
└─────────────────────────────────┘
```

**Behavior:**
- On success → redirect to `/`
- Show inline error on wrong credentials: `"Invalid email or password"`
- Show spinner on button while submitting

---

#### `/register` — Register Page

**Purpose:** Create a new account.

**Layout:** Same as login page.

```
┌─────────────────────────────────┐
│          gitDeploy              │
│                                 │
│  Create your account            │
│                                 │
│  Username                       │
│  [________________________]     │
│                                 │
│  Email                          │
│  [________________________]     │
│                                 │
│  Password                       │
│  [________________________] 👁  │
│                                 │
│  Confirm Password               │
│  [________________________] 👁  │
│                                 │
│  [       Create Account  ]      │
│                                 │
│  Already have an account? Login │
└─────────────────────────────────┘
```

**Behavior:**
- On success → redirect to `/login` with success toast: `"Account created. Please sign in."`

---

### Dashboard

---

#### `/` — Dashboard Page

**Purpose:** Overview of user's deployments at a glance.

**Layout:** App shell (sidebar + topbar) + main content area.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  SIDEBAR          │  TOPBAR: "Dashboard"                  [New App +]   │
│                   │──────────────────────────────────────────────────────│
│  ◉ Dashboard      │                                                      │
│  ☰ Apps           │  ┌─────────┐  ┌─────────┐  ┌─────────┐             │
│  ⚙ Settings       │  │ Total   │  │ Running │  │ Errors  │             │
│                   │  │  Apps   │  │         │  │         │             │
│  ──────────────── │  │   12    │  │    9    │  │    2    │             │
│                   │  └─────────┘  └─────────┘  └─────────┘             │
│  [User Avatar]    │                                                      │
│  alice            │  Recent Deployments                                  │
│  Free plan        │  ┌──────────────────────────────────────────────┐   │
│                   │  │ my-api          running    app-1.domain.com  │   │
│                   │  │ frontend-app    error      app-2.domain.com  │   │
│                   │  │ backend-svc     created    app-3.domain.com  │   │
│                   │  └──────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

**Stats cards:** Total Apps, Running, Error count. Fetch from `/api/v1/apps/list/`.

---

### Apps

---

#### `/apps` — Apps List Page

**Purpose:** Show all user's apps with status, quick actions.

**Layout:** Page header + filter bar + app grid/list.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Apps                                              [+ New App]           │
│                                                                          │
│  Filter: [All ▼]  Search: [________________]                            │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  my-api                                          ● running      │    │
│  │  github.com/alice/my-api  ·  main  ·  app-1.domain.com         │    │
│  │  Updated 2 hours ago            [Visit] [Redeploy] [⋯]         │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │  frontend-app                                    ● error        │    │
│  │  github.com/alice/frontend  ·  develop  ·  app-2.domain.com    │    │
│  │  Updated 5 hours ago            [Visit] [Redeploy] [⋯]         │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │  worker-service                                  ○ created      │    │
│  │  github.com/alice/worker  ·  main  ·  Not deployed yet         │    │
│  │  Updated 1 day ago                     [Deploy] [⋯]            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Showing 3 of 3 apps                                                     │
└──────────────────────────────────────────────────────────────────────────┘
```

**Behaviors:**
- Filter dropdown: `All | Running | Error | Created | Prepared`
- Search: client-side filter by app name or repo URL
- `[Visit]` → opens `http://app-{id}.yourdomain.com` in new tab
- `[Redeploy]` → navigates to `/apps/:id/deploy`
- `[⋯]` menu → `View Details`, `Redeploy`, `Delete`
- `Delete` → confirmation dialog before calling DELETE API

---

#### `/apps/new` — New App Page

**Purpose:** Create a new app record (does NOT deploy yet).

**Layout:** Single-column form card, max-w-2xl centered.

```
┌──────────────────────────────────────────────┐
│  ← Back to Apps                              │
│                                              │
│  Create New App                              │
│  Link a GitHub repository to deploy         │
│                                              │
│  ──────── Basic Info ────────               │
│                                              │
│  App Name *                                  │
│  [________________________________]          │
│  Hint: A display name for your app           │
│                                              │
│  GitHub Repository URL *                     │
│  [________________________________]          │
│  Hint: Must be a public GitHub repo          │
│  e.g. https://github.com/user/repo.git       │
│                                              │
│  Branch                                      │
│  [main___________________________]           │
│  Hint: Branch to deploy from                 │
│                                              │
│  ──────── Container Config ────────          │
│                                              │
│  Container Port *                            │
│  [8000____________________________]          │
│  Hint: Port your app listens on inside       │
│  the container (e.g. 8000 for FastAPI,       │
│  3000 for Node.js, 80 for nginx)             │
│                                              │
│  Source Directory                            │
│  [._______________________________]          │
│  Hint: Path within the repo to build from   │
│  (use "." for repo root)                     │
│                                              │
│  Dockerfile Path                             │
│  [Dockerfile____________________]            │
│  Hint: Relative path to your Dockerfile      │
│                                              │
│  ──────── Environment Variables ────────     │
│                                              │
│  Environment Variables                       │
│  ┌──────────────┐  ┌──────────────┐  [✕]    │
│  │ KEY          │  │ VALUE        │          │
│  └──────────────┘  └──────────────┘          │
│  [+ Add Variable]                            │
│                                              │
│  [Cancel]          [Create App →]            │
└──────────────────────────────────────────────┘
```

**On Success:**
- Toast: `"App created successfully"`
- Redirect to `/apps/:id` (app detail page)
- Show a banner on detail page: `"App created. Ready to deploy."`

---

#### `/apps/:id` — App Detail Page

**Purpose:** Full view of a single app — status, config, links, actions.

**Layout:** Two-column on desktop: left = main info, right = metadata sidebar.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ← Apps   /   my-api                                                     │
│                                                                          │
│  my-api                                  ● running                       │
│  github.com/alice/my-api                                                 │
│                                                                          │
│  [Deploy / Redeploy]   [Visit App ↗]   [⋯ More]                         │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  LIVE URL                                                                │
│  http://app-1.yourdomain.com                        [Copy]              │
│                                                                          │
│  ──────── Deployment Info ────────                                       │
│                                                                          │
│  │ Branch         │ main                          │                      │
│  │ Repo URL       │ https://github.com/alice/...  │                      │
│  │ Dockerfile     │ Dockerfile                    │                      │
│  │ Source Dir     │ .                             │                      │
│  │ Container Port │ 8000                          │                      │
│  │ Internal Port  │ 10023                         │                      │
│  │ Status         │ ● running                     │                      │
│  │ Subdomain      │ app-1                         │                      │
│  │ Created At     │ March 10, 2026 14:32          │                      │
│  │ Last Updated   │ March 12, 2026 09:15          │                      │
│                                                                          │
│  ──────── Environment Variables ────────                                 │
│                                                                          │
│  │ NODE_ENV       │ production                    │                      │
│  │ PORT           │ 8000                          │                      │
│  (shown as masked ••••••• with toggle to reveal)                         │
│                                                                          │
│  ──────── Danger Zone ────────                                           │
│                                                                          │
│  Delete this app                                                         │
│  This will stop and remove the container, image, and all app data.      │
│  [Delete App]  ← red destructive button                                  │
└──────────────────────────────────────────────────────────────────────────┘
```

**Delete flow:**
```
Click "Delete App"
    └── Confirmation Dialog:
        "Are you sure you want to delete my-api?
         This action cannot be undone."
        [Cancel]  [Delete App]
        ↓ on confirm → DELETE /api/v1/apps/delete/:id
        ↓ success → redirect to /apps + toast "App deleted"
```

---

### Deploy

---

#### `/apps/:id/deploy` — Deploy Page

**Purpose:** Trigger a deployment with optional config overrides.

**Layout:** Single-column form card, max-w-2xl. Pre-fill from existing app config.

```
┌──────────────────────────────────────────────┐
│  ← my-api                                    │
│                                              │
│  Deploy my-api                               │
│  Configure and trigger a new deployment      │
│                                              │
│  ──────── Git Config ────────               │
│                                              │
│  Branch                                      │
│  [main___________________________]           │
│  Hint: Override branch for this deployment   │
│                                              │
│  Source Directory                            │
│  [._______________________________]          │
│                                              │
│  Dockerfile Path                             │
│  [Dockerfile____________________]            │
│                                              │
│  ──────── Build Options ────────             │
│                                              │
│  Build Arguments                             │
│  ┌──────────────┐  ┌──────────────┐  [✕]    │
│  │ ARG KEY      │  │ VALUE        │          │
│  └──────────────┘  └──────────────┘          │
│  [+ Add Build Arg]                           │
│                                              │
│  ┌────────────────────────────────────┐      │
│  │ ☐  Force Rebuild                   │      │
│  │    Ignore existing Docker image    │      │
│  └────────────────────────────────────┘      │
│                                              │
│  ┌────────────────────────────────────┐      │
│  │ ☐  Clear Cache                     │      │
│  │    Build without Docker cache      │      │
│  └────────────────────────────────────┘      │
│                                              │
│  ──────── Environment Variables ────────     │
│                                              │
│  (Pre-filled from app config)                │
│  ┌──────────────┐  ┌──────────────┐  [✕]    │
│  │ NODE_ENV     │  │ production   │          │
│  └──────────────┘  └──────────────┘          │
│  [+ Add Variable]                            │
│                                              │
│  ──────── Deploy ────────                    │
│                                              │
│  ⚠ This will stop the current container     │
│    and start a new one.                      │
│                                              │
│  [Cancel]      [🚀 Deploy Now]               │
└──────────────────────────────────────────────┘
```

**Deploy in-progress state:**

```
┌──────────────────────────────────────────────┐
│                                              │
│  Deploying my-api...                         │
│                                              │
│  ▸ Validating repository    ✓               │
│  ▸ Cloning / pulling code   ✓               │
│  ▸ Building Docker image    ⏳ (in progress) │
│  ▸ Allocating port          ○               │
│  ▸ Starting container       ○               │
│                                              │
│  (Note: backend processes are sync —         │
│   poll GET /apps/:id for status change)      │
│                                              │
│  [Cancel deployment]                         │
└──────────────────────────────────────────────┘
```

> **Backend note:** The deploy endpoint is synchronous. Poll `GET /api/v1/apps/:id` every 3 seconds until status changes from what it was. Show animated progress steps while polling.

**On success:** Redirect to `/apps/:id` + toast `"Deployed successfully"`
**On error:** Show error message from API response + `error_code` + `message`.

---

### Settings

---

#### `/settings` — Settings Page

**Purpose:** Manage account details, API access, danger zone.

**Layout:** Tabs or sections on a single page.

```
┌──────────────────────────────────────────────┐
│  Settings                                    │
│                                              │
│  ──────── Profile ────────                   │
│                                              │
│  Username                                    │
│  [alice____________________________]         │
│                                              │
│  Email                                       │
│  [alice@example.com_______________]          │
│                                              │
│  [Save Changes]                              │
│                                              │
│  ──────── Change Password ────────           │
│                                              │
│  Current Password                            │
│  [________________________] 👁              │
│                                              │
│  New Password                                │
│  [________________________] 👁              │
│                                              │
│  Confirm New Password                        │
│  [________________________] 👁              │
│                                              │
│  [Update Password]                           │
│                                              │
│  ──────── API Access ────────                │
│                                              │
│  Your API Key                                │
│  [sk_live_••••••••••••]  [Copy] [Reveal]    │
│                                              │
│  [Regenerate Key] ← confirms before regen   │
│                                              │
│  ──────── Plan ────────                      │
│                                              │
│  Current Plan:  Free                         │
│  Upgrade for more apps and resources         │
│                                              │
│  ──────── Danger Zone ────────               │
│                                              │
│  Delete Account                              │
│  This will delete all your apps and data.   │
│  [Delete My Account] ← destructive          │
└──────────────────────────────────────────────┘
```

---

## 6. Forms — Complete Field Reference

### Form: Create App (`POST /api/v1/apps/create`)

| Field                  | Label                    | Type       | Required | Default      | Validation                                              |
|------------------------|--------------------------|------------|----------|--------------|---------------------------------------------------------|
| `name`                 | App Name                 | text       | Yes      | —            | 3–255 chars, alphanumeric + hyphens                     |
| `repo_url`             | GitHub Repository URL    | text (url) | Yes      | —            | Must start with `https://github.com/`, end with `.git` |
| `branch`               | Branch                   | text       | No       | `main`       | Non-empty string                                        |
| `container_port`       | Container Port           | number     | Yes      | `8000`       | Integer 1–65535                                         |
| `source_dir`           | Source Directory         | text       | No       | `.`          | Non-empty string                                        |
| `dockerfile_path`      | Dockerfile Path          | text       | No       | `Dockerfile` | Non-empty string                                        |
| `env` (key-value rows) | Environment Variables    | key-value  | No       | `{}`         | Keys: UPPER_SNAKE_CASE recommended                      |

---

### Form: Deploy App (`POST /api/v1/apps/:id/deploy`)

| Field                  | Label                    | Type      | Required | Default         | Validation            |
|------------------------|--------------------------|-----------|----------|-----------------|-----------------------|
| `branch`               | Branch                   | text      | No       | App's branch    | Non-empty if provided |
| `source_dir`           | Source Directory         | text      | No       | App's source    | Non-empty if provided |
| `dockerfile_path`      | Dockerfile Path          | text      | No       | App's Dockerfile| Non-empty if provided |
| `env` (key-value rows) | Environment Variables    | key-value | No       | App's env       | —                     |
| `build_args`           | Build Arguments          | key-value | No       | `{}`            | Docker ARG format     |
| `force_rebuild`        | Force Rebuild            | checkbox  | No       | `false`         | —                     |
| `clear_cache`          | Clear Build Cache        | checkbox  | No       | `false`         | —                     |

---

### Form: Login (`POST /api/v1/auth/login`)

| Field      | Label    | Type     | Required | Validation                 |
|------------|----------|----------|----------|----------------------------|
| `email`    | Email    | email    | Yes      | Valid email format         |
| `password` | Password | password | Yes      | Min 8 chars                |

---

### Form: Register (`POST /api/v1/auth/register`)

| Field              | Label            | Type     | Required | Validation                          |
|--------------------|------------------|----------|----------|-------------------------------------|
| `username`         | Username         | text     | Yes      | 3–50 chars, alphanumeric + _        |
| `email`            | Email            | email    | Yes      | Valid email format                  |
| `password`         | Password         | password | Yes      | Min 8 chars, 1 uppercase, 1 number  |
| `confirm_password` | Confirm Password | password | Yes      | Must match `password`               |

---

### Form: Update Profile (`PUT /api/v1/auth/me`)

| Field      | Label    | Type  | Required | Validation          |
|------------|----------|-------|----------|---------------------|
| `username` | Username | text  | No       | 3–50 chars          |
| `email`    | Email    | email | No       | Valid email format  |

---

### Form: Change Password (`PUT /api/v1/auth/me/password`)

| Field              | Label             | Type     | Required | Validation                |
|--------------------|-------------------|----------|----------|---------------------------|
| `current_password` | Current Password  | password | Yes      | Non-empty                 |
| `new_password`     | New Password      | password | Yes      | Min 8 chars               |
| `confirm_password` | Confirm New       | password | Yes      | Must match `new_password` |

---

## 7. API Integration

### Axios Client Setup

```ts
// src/api/client.ts
import axios from "axios";
import { useAuthStore } from "@/store/authStore";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,   // e.g. http://localhost:8000
  withCredentials: true,                    // send HttpOnly refresh token cookie
});

// Attach access token to every request
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Auto-refresh on 401
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      try {
        const { data } = await axios.post(
          `${import.meta.env.VITE_API_URL}/api/v1/auth/refresh`,
          {},
          { withCredentials: true }
        );
        useAuthStore.getState().setToken(data.access_token);
        original.headers.Authorization = `Bearer ${data.access_token}`;
        return api(original);
      } catch {
        useAuthStore.getState().clear();
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export default api;
```

### API Functions

```ts
// src/api/apps.ts
import api from "./client";

export const appsApi = {
  list: (params?: { status?: string; page?: number; size?: number }) =>
    api.get("/api/v1/apps/list/", { params }),

  get: (id: number) =>
    api.get(`/api/v1/apps/${id}`),

  create: (data: CreateAppPayload) =>
    api.post("/api/v1/apps/create", data),

  deploy: (id: number, data: DeployAppPayload) =>
    api.post(`/api/v1/apps/${id}/deploy`, data),

  delete: (id: number) =>
    api.delete(`/api/v1/apps/delete/${id}`),
};
```

### TypeScript Types

```ts
// src/types/app.ts
export type AppStatus = "created" | "running" | "error" | "prepared";

export interface AppListItem {
  id: number;
  name: string;
  subdomain: string;
  container_port: number;
  status: AppStatus;
  build_path: string;
  branch: string;
  repo_url: string;
}

export interface AppDetail extends AppListItem {
  internal_port: number | null;
  dockerfile_path: string;
  created_at: string;
  updated_at: string;
  env: Record<string, string>;
}

export interface CreateAppPayload {
  name: string;
  repo_url: string;
  container_port: number;
  branch?: string;
  source_dir?: string;
  dockerfile_path?: string;
  env?: Record<string, string>;
}

export interface DeployAppPayload {
  branch?: string;
  source_dir?: string;
  dockerfile_path?: string;
  env?: Record<string, string>;
  build_args?: Record<string, string>;
  force_rebuild?: boolean;
  clear_cache?: boolean;
}
```

### API Error Format (from backend)

```ts
// All errors from backend:
{
  "error_code": 1004,
  "message": "Repository not found or is private",
  "status_code": 404
}

// Handle in UI:
export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    return error.response?.data?.message ?? "Something went wrong";
  }
  return "Network error";
}
```

### Common Error Codes to Handle in UI

| Error Code | Meaning                             | UI Message                                     |
|------------|-------------------------------------|------------------------------------------------|
| 1000       | Invalid repo URL                    | `"Please enter a valid GitHub URL"`            |
| 1004       | Repo not found or private           | `"Repository not found or is private"`         |
| 1006       | Private repo not supported          | `"Only public repositories are supported"`     |
| 1007       | Git clone failed                    | `"Failed to clone repository"`                 |
| 1009       | Branch not found                    | `"Branch not found in repository"`             |
| 2000       | Dockerfile not found                | `"Dockerfile not found at specified path"`     |
| 2002       | Docker build failed                 | `"Build failed. Check your Dockerfile"`        |
| 2006       | No ports available                  | `"No available ports (server at capacity)"`    |
| 3000       | App not found                       | `"App not found"`                              |

---

## 8. Auth Flow (Frontend)

```
USER OPENS APP
    │
    ▼
Check Zustand: accessToken?
    │
    ├── YES → render app normally
    │
    └── NO → redirect to /login
              │
              ▼
         User submits login form
              │
              ▼
         POST /api/v1/auth/login
              │
              ├── 200 OK → { access_token }
              │   ├── Store access_token in Zustand (memory only, not localStorage)
              │   ├── Refresh token set as HttpOnly cookie by server
              │   └── Redirect to /
              │
              └── 401 → show "Invalid email or password"


EVERY API REQUEST
    │
    ▼
Axios interceptor adds: Authorization: Bearer <access_token>
    │
    ├── 200 → OK, proceed
    │
    └── 401 → interceptor auto-calls POST /api/v1/auth/refresh
              │
              ├── 200 → new access_token → retry original request
              │
              └── 401 → clear store → redirect to /login
```

### Zustand Auth Store

```ts
// src/store/authStore.ts
import { create } from "zustand";

interface AuthState {
  accessToken: string | null;
  user: { username: string; email: string; role: string } | null;
  setToken: (token: string) => void;
  setUser: (user: AuthState["user"]) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  setToken: (token) => set({ accessToken: token }),
  setUser: (user) => set({ user }),
  clear: () => set({ accessToken: null, user: null }),
}));
```

---

## 9. Docker Setup

The React app is built as a static bundle and served via Nginx inside Docker.

### `Dockerfile`

```dockerfile
# ────────────────────────────────────────
# Stage 1: Build the React app
# ────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies (cached layer)
COPY package.json package-lock.json ./
RUN npm ci

# Copy source + build
COPY . .
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ────────────────────────────────────────
# Stage 2: Serve with Nginx
# ────────────────────────────────────────
FROM nginx:1.27-alpine AS runner

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

# Copy Nginx config
COPY nginx.conf /etc/nginx/conf.d/app.conf

# Copy built app
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  # ── React Frontend ──────────────────────────────────────────
  frontend:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        VITE_API_URL: ${VITE_API_URL:-http://localhost:8000}
    image: gitdeploy-ui:latest
    container_name: gitdeploy-frontend
    ports:
      - "3000:80"        # host:container
    restart: unless-stopped
    environment:
      - NGINX_HOST=localhost
    networks:
      - gitdeploy-net

  # ── Backend API (reference — run separately) ─────────────────
  # Uncomment if running full stack with this compose file
  # backend:
  #   image: gitdeploy-api:latest
  #   container_name: gitdeploy-backend
  #   ports:
  #     - "8000:8000"
  #   networks:
  #     - gitdeploy-net

networks:
  gitdeploy-net:
    driver: bridge
```

### Build & Run Commands

```bash
# Development
npm run dev

# Build image
docker build \
  --build-arg VITE_API_URL=http://localhost:8000 \
  -t gitdeploy-ui:latest .

# Run container
docker run -p 3000:80 gitdeploy-ui:latest

# With docker-compose
docker-compose up --build
docker-compose down
```

---

## 10. Nginx Configuration

### `nginx.conf` — Serves React SPA + Proxies API

```nginx
server {
    listen 80;
    server_name _;

    # ── Serve React static files ──────────────────────────────
    root /usr/share/nginx/html;
    index index.html;

    # ── SPA routing: always serve index.html for unknown paths ─
    location / {
        try_files $uri $uri/ /index.html;
    }

    # ── Proxy API requests to backend ─────────────────────────
    # Uncomment this block when frontend and backend
    # are deployed behind the same Nginx reverse proxy
    #
    # location /api/ {
    #     proxy_pass          http://gitdeploy-backend:8000;
    #     proxy_http_version  1.1;
    #     proxy_set_header    Host              $host;
    #     proxy_set_header    X-Real-IP         $remote_addr;
    #     proxy_set_header    X-Forwarded-For   $proxy_add_x_forwarded_for;
    #     proxy_set_header    X-Forwarded-Proto $scheme;
    #     proxy_read_timeout  90;
    # }

    # ── Gzip compression ──────────────────────────────────────
    gzip on;
    gzip_types text/plain text/css application/json application/javascript
               text/javascript image/svg+xml;
    gzip_min_length 1024;

    # ── Cache static assets ───────────────────────────────────
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # ── Security headers ──────────────────────────────────────
    add_header X-Frame-Options         "SAMEORIGIN"   always;
    add_header X-Content-Type-Options  "nosniff"      always;
    add_header X-XSS-Protection        "1; mode=block" always;
    add_header Referrer-Policy         "strict-origin-when-cross-origin" always;
}
```

### Future: Full Nginx Reverse Proxy (Production)

When deploying both frontend and backend behind a single domain:

```nginx
# /etc/nginx/sites-available/gitdeploy.conf

# ── Frontend (React) ──────────────────────────────────────────
server {
    listen 80;
    server_name app.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
    }
}

# ── Backend (FastAPI) ─────────────────────────────────────────
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass          http://127.0.0.1:8000;
        proxy_set_header    Host            $host;
        proxy_set_header    X-Real-IP       $remote_addr;
        proxy_set_header    X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}

# ── Deployed Apps (subdomain routing) ────────────────────────
# Each deployed app gets: app-{id}.yourdomain.com
server {
    listen 80;
    server_name ~^app-(?<app_id>\d+)\.yourdomain\.com$;

    location / {
        # Port is dynamically assigned — backend manages this config
        # Placeholder: backend writes port here on deploy
        proxy_pass http://127.0.0.1:$app_port;
    }
}
```

---

## 11. Environment Variables

### `.env.example`

```env
# Backend API base URL (no trailing slash)
# Development: http://localhost:8000
# Production:  https://api.yourdomain.com
VITE_API_URL=http://localhost:8000

# App domain (used to construct live URLs: app-{id}.VITE_APP_DOMAIN)
# Development: localhost
# Production:  yourdomain.com
VITE_APP_DOMAIN=localhost
```

### `.env.development`

```env
VITE_API_URL=http://localhost:8000
VITE_APP_DOMAIN=localhost
```

### `.env.production`

```env
VITE_API_URL=https://api.yourdomain.com
VITE_APP_DOMAIN=yourdomain.com
```

### Using in Code

```ts
// Construct live app URL
const liveUrl = `http://app-${app.id}.${import.meta.env.VITE_APP_DOMAIN}`;
```

### Vite Config

```ts
// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      // Dev proxy: forward /api/* to FastAPI (avoids CORS in dev)
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
```

---

## Quick Start (Dev)

```bash
git clone <repo>
cd gitdeploy-ui

cp .env.example .env.development
# Edit VITE_API_URL to point to running backend

npm install
npm run dev
# → http://localhost:5173
```

## Quick Start (Docker)

```bash
docker-compose up --build
# Frontend → http://localhost:3000
```

---

*Spec version: 1.0 | Last updated: 2026-03-12 | Backend ref: gitDeploy FastAPI API v1*
