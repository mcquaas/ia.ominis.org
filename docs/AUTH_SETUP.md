# Ominis Auth Setup Guide

This guide covers the configuration of authentication features: email/SMS verification, password reset, and Google OAuth.

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

## 2. Email Service (Strapi)

Strapi uses providers for sending emails. Configure in the admin panel or via environment variables.

### Option A: Nodemailer (SMTP)

1. Install the provider:
   ```bash
   cd backend && npm install @strapi/provider-email-nodemailer
   ```

2. Configure in `config/plugins.js`:
   ```javascript
   module.exports = ({ env }) => ({
     // ... existing config
     email: {
       config: {
         provider: 'nodemailer',
         providerOptions: {
           host: env('SMTP_HOST', 'smtp.example.com'),
           port: env.int('SMTP_PORT', 587),
           auth: {
             user: env('SMTP_USER'),
             pass: env('SMTP_PASS'),
           },
           secure: env.bool('SMTP_SECURE', false),
         },
         settings: {
           defaultFrom: env('SMTP_FROM', 'noreply@ominis.org'),
           defaultReplyTo: env('SMTP_REPLY_TO', 'support@ominis.org'),
         },
       },
     },
   });
   ```

3. Add to `.env`:
   ```
   SMTP_HOST=smtp.sendgrid.net
   SMTP_PORT=587
   SMTP_USER=apikey
   SMTP_PASS=your-sendgrid-api-key
   SMTP_FROM=noreply@ominis.org
   ```

### Option B: SendGrid

1. Install: `npm install @strapi/provider-email-sendgrid`
2. Configure with SendGrid API key in plugins
3. See [Strapi SendGrid docs](https://market.strapi.io/providers/@strapi-provider-email-sendgrid)

### Option C: AWS SES

1. Install: `npm install @strapi/provider-email-amazon-ses`
2. Configure with AWS credentials

### Email Templates

Configure in **Admin Panel → Users & Permissions → Email Templates**:
- **Email address confirmation**: Sent when `Enable email confirmation` is ON
- **Reset password**: Sent when user requests password reset

Configure **Advanced Settings**:
- **Reset password page**: `https://ia.ominis.org/reset-password`
- **Enable email confirmation**: Toggle as needed
- **Redirection url**: `https://ia.ominis.org/login` (after email confirmation)

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

The following custom Strapi routes need to be implemented (via plugin extension):

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

- **Forgot password**: User enters email → Strapi sends reset link
- **Reset password**: User clicks link → lands on `/reset-password?code=xxx` → enters new password

### Extended Flow (Email + Phone)

To support phone-based reset:

1. Create custom route `POST /api/auth/forgot-password-phone`
2. Look up user by `phone`, generate reset token, send SMS with link
3. Same reset page works (code in URL)

---

## 5. Google OAuth (Google Cloud Setup)

### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable **Google+ API** or **Google Identity** (if prompted)

### Step 2: Configure OAuth Consent Screen

1. Navigate to **APIs & Services → OAuth consent screen**
2. Choose **External** (for public users)
3. Fill required fields:
   - App name: `Ominis AI`
   - User support email: your email
   - Developer contact: your email
4. Add scopes: `email`, `profile`, `openid`
5. Add test users during development (optional)

### Step 3: Create OAuth 2.0 Credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. Application type: **Web application**
4. Name: `Ominis Auth`
5. **Authorized JavaScript origins**:
   - `https://ia.ominis.org`
   - `http://localhost:3000` (development)
6. **Authorized redirect URIs**:
   - `https://api.ominis.org/v1/api/connect/google/callback`
   - `https://admin.ominis.org/v1/api/connect/google/callback` (if using admin subdomain)
   - `http://localhost:1337/api/connect/google/callback` (local dev)

7. Copy **Client ID** and **Client Secret**

### Step 4: Configure Strapi

1. Open Strapi Admin: `https://admin.ominis.org/admin`
2. Go to **Settings → Users & Permissions → Providers**
3. Edit **Google**
4. Enable: **ON**
5. **Client ID**: paste from Google Console
6. **Client Secret**: paste from Google Console
7. **Redirect URL to your front-end app**: `https://ia.ominis.org/connect/google/redirect`
   - For local dev: `http://localhost:3000/connect/google/redirect`
8. Save

### Step 5: Server URL

Ensure `config/server.js` has the correct absolute URL:

```javascript
module.exports = ({ env }) => ({
  host: env('HOST', '0.0.0.0'),
  port: env.int('PORT', 1337),
  url: env('PUBLIC_URL', 'https://api.ominis.org/v1'),
  // ...
});
```

`PUBLIC_URL` must match your Strapi API base (used for OAuth redirects).

### Step 6: Frontend

The login page already includes "Continuar con Google". It redirects to:

```
{STRAPI_URL}/v1/api/connect/google
```

After successful auth, Strapi redirects to the frontend URL with the JWT. The page `/connect/google/redirect` handles the callback and stores the token.

---

## Checklist

- [ ] Add `phone` column to database (migration or sync)
- [ ] Configure email provider (Nodemailer/SendGrid/SES)
- [ ] Set up Twilio account and add env vars
- [ ] Implement custom phone verification endpoints (optional)
- [ ] Implement custom forgot-password-phone endpoint (optional)
- [ ] Create Google Cloud project and OAuth credentials
- [ ] Configure Google provider in Strapi admin
- [ ] Set correct redirect URIs in Google Console
- [ ] Configure reset password page URL in Strapi advanced settings
- [ ] Enable email confirmation in Strapi if desired
