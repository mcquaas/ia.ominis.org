# LibreChat source (frontend-librechat)

The full [LibreChat](https://github.com/danny-avila/LibreChat) repo is in this workspace as a **git submodule** at **`frontend-librechat/`**. All UI and API code for chat.ominis.org lives there so you can search, edit strings, and change behavior beyond CSS overrides.

## Layout

| Path | Purpose |
|------|--------|
| `frontend-librechat/client/` | **Frontend** (React, Vite). Chat UI, components, hooks, i18n. |
| `frontend-librechat/api/` | Node backend (used by the official Docker image; we use api.ominis.org for completions). |
| `frontend-librechat/packages/` | Shared packages (e.g. `librechat-data-provider`). |

## Clone with submodule

If you cloned without submodules:

```bash
git submodule update --init --recursive
```

## Local development

First time (or if you see “Failed to resolve entry for package @librechat/client”): build the workspace packages so the client can resolve `@librechat/client` and `librechat-data-provider`:

```bash
cd frontend-librechat
npm ci
export PATH="$PWD/node_modules/.bin:$PATH"
npm run build:data-provider
npm run build:client-package
```

**Local env (optional):** To keep LibreChat env separate from other frontends (e.g. `frontend/`), copy `.env.local.example` to `.env.local`. Vite loads from `frontend-librechat/` only (`envDir: '../'`), so it never reads the repo root or `frontend/.env`. Use `.env.local` for port/host overrides when running the client dev server.

Then start the frontend:

```bash
npm run frontend:dev   # client at http://localhost:3090
```

Backend is expected at http://localhost:3080 (or point env to api.ominis.org for completions).

## Production (chat.ominis.org)

You can ship either **overlay-only** (official image + CSS/logo) or **from-source** (your compiled client).

### Option A: Overlay-only (quick)

Official LibreChat image + overrides from `infrastructure/librechat-ominis-build/` (CSS, logo, footer script). No compilation of `frontend-librechat`.

- Build: `./infrastructure/28-build-chat-image.sh`
- See [CHAT_OMINIS.md](CHAT_OMINIS.md).

### Option B: From-source (full tailoring)

Build the client from `frontend-librechat/` and use it in the Docker image. Any code or string changes in `frontend-librechat/client` are included.

- **Local build (test):**  
  `./infrastructure/librechat-ominis-build/build-from-source-local.sh`  
  (from repo root; produces `librechat-ominis:latest`)

- **Build on chat server and deploy:**  
  `./infrastructure/28b-build-chat-image-from-source.sh`  
  Syncs `frontend-librechat` + overrides to the EC2, runs Docker build there (≈10–15 min), tags `librechat-ominis:latest`.

Then set `CHAT_IMAGE=librechat-ominis:latest` in `infrastructure/librechat-chat/.env` and run `./infrastructure/26-sync-chat-librechat.sh`.

## Submodule commands

- **Update LibreChat to latest upstream:**  
  `cd frontend-librechat && git fetch origin main && git checkout main && git pull`
- **Pin a specific LibreChat version:**  
  `cd frontend-librechat && git checkout <tag-or-commit>`

## Ominis overrides (current deploy)

Theme and branding are still applied from:

- `infrastructure/librechat-ominis-build/overrides/ominis-overrides.css`
- `infrastructure/librechat-ominis-build/overrides/ominis-footer.js`
- `infrastructure/librechat-ominis-build/overrides/logo.svg`

Edit those for quick visual changes; edit code in `frontend-librechat/` for logic, copy, and structure.
