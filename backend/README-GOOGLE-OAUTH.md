# Google Drive Connector OAuth Setup Guide

## Overview
This guide explains how to set up the credentials and consent screen required for your KlarisAI backend to connect to Google Drive as a connector for each tenant via OAuth 2.0 (read-only access).

## Step 1: Create a Google Cloud Project
1. Sign in to https://console.cloud.google.com/
2. Create or select a project for KlarisAI connectors.

## Step 2: Enable Google Drive API
1. Go to "APIs & Services" > "Library".
2. Search for **Google Drive API** and click **Enable**.

## Step 3: Configure OAuth Consent Screen
1. Under "APIs & Services" > "OAuth consent screen", 
2. Select User Type: **Internal** (if G Suite domain), otherwise **External**.
3. Fill in app info (app name, user support email, etc.).
4. Add **Scopes**:
   - `https://www.googleapis.com/auth/drive.readonly`
5. Add test users (your Gmail for testing).

## Step 4: Create OAuth 2.0 Credentials
1. Go to "APIs & Services" > "Credentials".
2. Click **Create Credentials** > **OAuth client ID**.
3. Application type = **Web application**.
4. Name it (e.g., "Klaris Google Drive Backend").
5. **Authorized redirect URIs** (add this for local/dev):

       http://localhost:8000/tenants/<tenant_id>/connectors/google-drive/callback

   (Substitute `<tenant_id>` at runtime. For development/testing, `localhost:8000` is standard.)
6. Click **Create**.
7. Download/save your `client_id` and `client_secret`.

## Step 5: Update Environment Variables
Edit your `/backend/.env`:

```
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/tenants/<tenant_id>/connectors/google-drive/callback
```

*For production, use your production domain in place of localhost in the redirect URI.*

---

## Troubleshooting
- If you see a Google error about redirect URIs, make sure it matches **exactly**, including port, path, and scheme.
- Add every test user's Google email under "Test Users" if not using Internal mode.
- When launching from the frontend, the backend endpoint `/google-drive/authorize` will redirect users through the above consent screen.

---

## Security
- Never check secrets into git.
- Ensure you use the correct `.env` for each deployment.

---

For support, see Google’s [OAuth docs](https://developers.google.com/identity/protocols/oauth2/web-server) or contact an admin.
