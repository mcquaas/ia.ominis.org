# Ominis Auth Setup Guide

This guide covers the configuration of authentication features: email/SMS verification, password reset, and Google OAuth.

**Note:** The production backend is the Haystack API (FastAPI) at **api.ominis.org**. Use `NEXT_PUBLIC_API_URL=https://api.ominis.org` in the frontend.

## 1. Phone Field (Already Implemented)

The phone field has been added to user registration. Users can optionally provide a phone number during sign-up.

- **Backend**: User model extended with `phone`, `phoneVerified`, `emailVerified` fields
- **Frontend**: RegisterForm includes phone input
- **Config**: `phone` added to `register.allowedFields` in `config/plugins.js`

**Database migration**: Run a schema sync or create a migration to add the new columns to `up_users`:

```sql
-- For PostgreSQL
ALTER TABLE up_users ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
ALTER TABLE up_users ADD COLUMN IF NOT EXISTS "phoneVerified" BOOLEAN DEFAULT false;
ALTER TABLE up_users ADD COLUMN IF NOT EXISTS "emailVerified" BOOLEAN DEFAULT false;
```

---

## 2. Email Service

Email (password reset, verification) is configured in the **Haystack backend** (`backend-haystack`). Configure SMTP or your provider via the backend's environment variables and any email templates used by the auth routes. Reset password and confirmation URLs are set in backend config (e.g. redirect to `https://ia.ominis.org/reset-password`, `https://ia.ominis.org/login`).

---

## 3. Twilio (SMS Verification)

Twilio is used for phone verification and SMS-based password reset.

### Installation

```bash
cd backend && npm install twilio
```

### Environment Variables

Add to `backend/.env`:

```
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1234567890
```

### Custom Endpoints Needed

The following auth flows are implemented in the Haystack backend:

1. **POST /api/auth/send-phone-verification** – Send SMS with verification code
2. **POST /api/auth/verify-phone** – Verify code and set `phoneVerified: true`
3. **POST /api/auth/forgot-password-phone** – Send reset link via SMS (alternative to email)

### Example: Twilio Send SMS

```javascript
// In a custom controller or service
const twilio = require('twilio');
const client = twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN);

await client.messages.create({
  body: `Tu código de verificación Ominis: ${code}`,
  from: process.env.TWILIO_PHONE_NUMBER,
  to: userPhone,
});
```

---

## 4. Password Reset (Current + Extended)

### Current Flow (Email)

- **Forgot password**: User enters email → backend sends reset link
- **Reset password**: User clicks link → lands on `/reset-password?code=xxx` → enters new password

### Extended Flow (Email + Phone)

To support phone-based reset:

1. Create custom route `POST /api/auth/forgot-password-phone`
2. Look up user by `phone`, generate reset token, send SMS with link
3. Same reset page works (code in URL)

---

## 5. Google OAuth (Haystack backend + Google Cloud)

The backend (FastAPI) implements Google OAuth. The **return URL** that Google must redirect to is the **backend** callback URL, not the frontend.

### Return URL (Authorized redirect URI) for Google Cloud

Use this exact URI in Google Cloud Console → Credentials → your OAuth client → **Authorized redirect URIs**:

- **Production:** `https://api.ominis.org/v1/api/connect/google/callback`
- **Local dev:** `http://localhost:8000/v1/api/connect/google/callback` (if backend runs on port 8000)

Google sends the user to this URL after they sign in; the backend then exchanges the code for tokens and redirects the user to the frontend with the JWT.

### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing (e.g. "Ominis")
3. No need to enable a separate API for basic OAuth (email/profile/openid).

### Step 2: Configure OAuth Consent Screen

1. Navigate to **APIs & Services → OAuth consent screen**
2. Choose **External** (for public users)
3. Fill required fields:
   - App name: e.g. `Ominis AI`
   - User support email: your email
   - Developer contact: your email
4. Add scopes: `email`, `profile`, `openid`
5. Add test users during development if the app is in "Testing" (optional)

### Step 3: Create OAuth 2.0 Credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. Application type: **Web application**
4. Name: e.g. `Ominis G Auth`
5. **Authorized JavaScript origins**:
   - `https://ia.ominis.org`
   - `http://localhost:3000` (development)
6. **Authorized redirect URIs** (must match exactly):
   - `https://api.ominis.org/v1/api/connect/google/callback`
   - `http://localhost:8000/v1/api/connect/google/callback` (local dev)
7. Copy **Client ID** and **Client Secret**

### Step 4: Configure Backend (Haystack)

1. In the backend `.env` (or environment) set:
   - `GOOGLE_CLIENT_ID` = Client ID from Google Console
   - `GOOGLE_CLIENT_SECRET` = Client Secret from Google Console
   - `FRONTEND_URL` = `https://ia.ominis.org` (production) or `http://localhost:3000` (dev). This is where the backend redirects after successful Google login (to `/connect/google/redirect?jwt=...&user=...`).
   - `BACKEND_PUBLIC_URL` = `https://api.ominis.org` (production, optional). Use when the backend is behind a reverse proxy so the OAuth redirect_uri sent to Google is exactly `https://api.ominis.org/v1/api/connect/google/callback`.
2. Restart the backend. "Continuar con Google" will work if both Google credentials are set.

### Step 5: Frontend

The login page already includes "Continuar con Google". It redirects the user to:

```
{NEXT_PUBLIC_API_URL}/v1/api/connect/google
```

(e.g. `https://api.ominis.org/v1/api/connect/google`). After Google sign-in, the backend callback redirects to `{FRONTEND_URL}/connect/google/redirect?jwt=...&user=...`; the page at `/connect/google/redirect` stores the token and sends the user to `/c`.

---

## Checklist

- [ ] Add `phone` column to database (migration or sync)
- [ ] Configure email provider (Nodemailer/SendGrid/SES)
- [ ] Set up Twilio account and add env vars
- [ ] Implement custom phone verification endpoints (optional)
- [ ] Implement custom forgot-password-phone endpoint (optional)
- [ ] Create Google Cloud project and OAuth credentials
- [ ] Configure Google provider in backend (api.ominis.org)
- [ ] Set correct redirect URIs in Google Console
- [ ] Configure reset password page URL in backend settings
- [ ] Enable email confirmation in backend if desired
