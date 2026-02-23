# LibreChat + OIDC (single login with ia.ominis.org)

Registration and login happen only on **ia.ominis.org**. **chat.ominis.org** (LibreChat) uses OpenID Connect so users sign in with the same account.

## Flow

1. User opens **chat.ominis.org** → LibreChat redirects to the OIDC provider (api.ominis.org).
2. Backend redirects to **ia.ominis.org/login?next=...** (authorize URL).
3. User logs in on ia.ominis.org (email/password or Google).
4. Frontend redirects back to the backend with a JWT; backend issues an OIDC code and redirects to LibreChat.
5. LibreChat exchanges the code for tokens and the user is logged in. The LibreChat login screen is never used.

## Backend (api.ominis.org)

Add to `.env` (see backend-haystack/.env.example):

```env
OIDC_LIBRECHAT_CLIENT_ID=librechat
OIDC_LIBRECHAT_CLIENT_SECRET=<shared-secret>
OIDC_LIBRECHAT_REDIRECT_URIS=https://chat.ominis.org/oauth/openid/callback
```

Generate a strong secret (e.g. `openssl rand -hex 32`) and set the **same** value as `OPENID_CLIENT_SECRET` in LibreChat’s `.env`.

Endpoints (same behaviour under `/v1/oidc` and `/v1/oauth2`; LibreChat may use either):

- `GET /.well-known/openid-configuration` → discovery (issuer/URLs match the path used)
- `GET /authorize` → redirect to login, then back with code
- `POST /token` → exchange code for id_token / access_token
- `GET /userinfo` → user info for Bearer token

Allowed redirect URIs by default: `https://chat.ominis.org/oauth/openid/callback`, `https://chat.ominis.org/oauth/callback`. Override with `OIDC_LIBRECHAT_REDIRECT_URIS` (comma-separated).

## LibreChat (chat.ominis.org)

In `infrastructure/librechat-chat/.env`:

```env
# Use /v1/oidc or /v1/oauth2; discovery and issuer will match
OPENID_ISSUER=https://api.ominis.org/v1/oauth2
OPENID_CLIENT_ID=librechat
OPENID_CLIENT_SECRET=<same-as-backend>
OPENID_CALLBACK_URL=/oauth/callback
OPENID_SCOPE=openid profile email
OPENID_SESSION_SECRET=<random-string>
OPENID_BUTTON_LABEL=Iniciar sesión con Ominis

ALLOW_REGISTRATION=false
ALLOW_EMAIL_LOGIN=false
```

After changing `.env`, run `./infrastructure/26-sync-chat-librechat.sh` to sync and restart.

## CORS

Backend `ALLOWED_ORIGINS` must include `https://chat.ominis.org` (already in .env.example).

## Google login and OIDC

If the user logs in with “Continuar con Google” on ia.ominis.org, the current flow still redirects to `/c` after the Google callback. To support “next” (OIDC return) through the Google flow, the backend would need to pass the return URL in the OAuth state and the frontend would redirect to that URL with the JWT after the Google redirect. Until then, **email/password login** is the supported path for OIDC; Google users can use email/password or this can be extended later.
