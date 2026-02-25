# Chat.Ominis.org — Same backend as ia.ominis.org

Chat at **chat.ominis.org** uses the **same backend as ia.ominis.org**: **api.ominis.org** (Haystack). Only the UI is different (LibreChat instead of Next.js). Auth and all completions/RAG go to api.ominis.org.

## Architecture

- **Frontend:** LibreChat (Docker) on a dedicated EC2 (t3.small), branded as “Ominis”.
- **Backend (same as ia.ominis.org):** Haystack API at **api.ominis.org**:
  - **Auth:** OIDC so users log in with the same account as ia.ominis.org (no separate LibreChat registration).
  - **Completions/RAG:** `POST /v1/chat/completions` — same models, same RAG, same API keys.
- **On the chat server:** Only LibreChat API + MongoDB run locally to serve the UI and store **conversation history** (list of chats, messages). All “brain” and user identity live on api.ominis.org.

## Deploy

### 1. Create EC2 (once)

```bash
./infrastructure/25-deploy-chat-ec2.sh
```

This creates:

- EC2 in **mx-central-1** (t3.small, Ubuntu 24.04)
- Security group (22, 80, 443)
- Elastic IP (saved in `config/chat_server.txt`)

### 2. Backend CORS

Ensure the Haystack backend allows requests from chat.ominis.org:

- In backend `.env`:  
  `ALLOWED_ORIGINS=...,https://chat.ominis.org`
- Or run the CORS update script (if it’s extended for chat):  
  e.g. include `https://chat.ominis.org` in the list in `infrastructure/20f-update-backend-env-cors.sh` and run it.

### 3. LibreChat config and credentials

- Generate **CREDS_KEY** and **CREDS_IV** at:  
  https://librechat.ai/toolkit/creds_generator  
- Copy `infrastructure/librechat-chat/.env.example` to `infrastructure/librechat-chat/.env`.
- Set in `.env`:
  - `CREDS_KEY=...`
  - `CREDS_IV=...`
  - `APP_TITLE=Ominis`
  - `DOMAIN_SERVER=https://chat.ominis.org`
  - `MONGO_URI=mongodb://mongodb:27017/Ominis`
  - **OIDC** (recommended): same login as ia.ominis.org — see [LIBRECHAT_OIDC.md](LIBRECHAT_OIDC.md). Set `OPENID_CLIENT_SECRET` (same as backend `OIDC_LIBRECHAT_CLIENT_SECRET`), `ALLOW_REGISTRATION=false`, `ALLOW_EMAIL_LOGIN=false`.
  - **API key for completions:** `OMINIS_API_KEY=...` (create at ia.ominis.org → Profile → API keys). The LibreChat UI uses this to call api.ominis.org; same backend as ia.ominis.org.

### 4. Sync and run LibreChat

```bash
./infrastructure/26-sync-chat-librechat.sh
```

This syncs the contents of `infrastructure/librechat-chat/` to the EC2, starts Docker Compose (LibreChat + MongoDB), and configures Nginx for chat.ominis.org.

### 5. DNS and SSL

- Create an **A** record: **chat.ominis.org** → Elastic IP from `config/chat_server.txt`.
- On the chat server:

  ```bash
  ssh -i config/ominis-chat-key.pem ubuntu@<CHAT_ELASTIC_IP>
  sudo certbot --nginx -d chat.ominis.org
  ```

## Custom Ominis image (theme and logo)

Two ways to build the custom image:

### A) Overlay-only (CSS/logo on official image)

Fast; no compilation. Use after changing only overrides (CSS, logo, footer script).

1. **Build on chat server:**
   ```bash
   ./infrastructure/28-build-chat-image.sh
   ```
   Syncs `infrastructure/librechat-ominis-build/` and runs `docker build -t librechat-ominis:latest` (overlay Dockerfile).

2. **Use the image:** In `infrastructure/librechat-chat/.env` set `CHAT_IMAGE=librechat-ominis:latest`.

3. **Deploy:** `./infrastructure/26-sync-chat-librechat.sh`.

### B) From-source (your compiled client)

Use when you change code or strings in `frontend-librechat/`. Builds the client from source and overlays it on the official API image.

1. **Ensure submodule:** `git submodule update --init --recursive` (so `frontend-librechat/` exists).

2. **Build on chat server** (syncs frontend-librechat + overrides, runs Docker build; ~10–15 min):
   ```bash
   ./infrastructure/28b-build-chat-image-from-source.sh
   ```
   Or **build locally** (for testing): from repo root,  
   `./infrastructure/librechat-ominis-build/build-from-source-local.sh`  
   then push the image to your registry if you deploy from there.

3. **Use the image:** In `infrastructure/librechat-chat/.env` set `CHAT_IMAGE=librechat-ominis:latest`.

4. **Deploy:** `./infrastructure/26-sync-chat-librechat.sh`.

- **Overlay build context:** `infrastructure/librechat-ominis-build/` — `Dockerfile` (overlay), `overrides/`. See [FRONTEND_LIBRECHAT.md](FRONTEND_LIBRECHAT.md).
- **From-source:** `Dockerfile.from-source` (build context = repo root; see same doc).

## Look and feel (Ominis)

- **Branding:** `APP_TITLE=Ominis`, `DOMAIN_SERVER=https://chat.ominis.org`. No “LibreChat” in the UI.
- **Palette (ia.ominis.org reference):**  
  Background `#0a1628`, foreground `#f8fafc`, primary `#1e3a5f`, accent `#3b82f6`.  
  LibreChat’s default theme is used; with the custom image (see "Custom Ominis image" above), `ominis-overrides.css` applies these colors; without it, the default theme is used.

## Usage

- Users open **https://chat.ominis.org** and log in via **Ominis** (OIDC → same account as ia.ominis.org). No separate registration.
- Completions use the **same backend** (api.ominis.org): set **OMINIS_API_KEY** in `.env` (create key at ia.ominis.org → Profile → API keys). The custom endpoint “Ominis” in `librechat.yaml` points to api.ominis.org/v1. Models: **ominis-2.0**, **ominis-2.0-med**, **ominis-2.0-research-128k** (same as ia.ominis.org).

## Files

| File | Purpose |
|------|---------|
| **`frontend-librechat/`** | **Full LibreChat source** (git submodule). Edit UI/API here; see [FRONTEND_LIBRECHAT.md](FRONTEND_LIBRECHAT.md). |
| `infrastructure/25-deploy-chat-ec2.sh` | Create EC2 and write `config/chat_server.txt` |
| `infrastructure/26-sync-chat-librechat.sh` | Sync config, start LibreChat + Nginx on EC2 |
| `infrastructure/28-build-chat-image.sh` | Build overlay image on chat server (CSS/logo only) |
| `infrastructure/28b-build-chat-image-from-source.sh` | Build image from `frontend-librechat` source on chat server |
| `infrastructure/librechat-ominis-build/build-from-source-local.sh` | Build from-source image locally (repo root) |
| `infrastructure/librechat-ominis-build/` | Dockerfile, Dockerfile.from-source, overrides (CSS, logo) |
| `infrastructure/librechat-chat/librechat.yaml` | Custom endpoint “Ominis” → api.ominis.org/v1 |
| `infrastructure/librechat-chat/docker-compose.yml` | LibreChat + MongoDB (minimal) |
| `infrastructure/librechat-chat/.env.example` | Env template (CREDS_KEY, CREDS_IV, APP_TITLE, etc.) |
| `config/chat_server.txt` | EC2 instance ID, Elastic IP, domain (generated by 25) |

## Login and 403 "login_required"

With **OIDC**, users log in on ia.ominis.org; no LibreChat login. The backend (api.ominis.org) treats a valid API key as the key’s owner. Requests from chat.ominis.org with `OMINIS_API_KEY` do not get `403 login_required`.

## Ominis RAG and search

`POST /v1/chat/completions` uses **Ominis RAG by default** (`rag_search=true`). Optional body fields: `rag_search`, `web_search`, `pubmed_search`, `openscholar_search` (defaults: RAG on, others off). So chat.ominis.org gets RAG-augmented answers by default.

## Backend endpoint

The Haystack backend exposes an OpenAI-compatible stream at:

- **POST /v1/chat/completions**  
  Same auth as other query endpoints (X-API-Key or Bearer).  
  Request/response follow the usual OpenAI chat completions format; the backend streams via the existing query-stream pipeline.
