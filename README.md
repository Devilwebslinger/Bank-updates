# Background push service

This Cloudflare Worker is the server half of Web Push. The browser subscribes through the Push API, the Worker stores subscriptions in D1, and the GitHub Actions updater can call `/notify` to send an alert. Web Push requires an active service worker and an application server; the subscription endpoint is a capability URL and should be kept private.

## 1. Create D1

```bash
npx wrangler d1 create bank-exam-push
npx wrangler d1 execute bank-exam-push --remote --file=schema.sql
```
Copy the returned database ID into `wrangler.toml`.

## 2. Install and deploy

```bash
npm install
npx wrangler secret put VAPID_SUBJECT
npx wrangler secret put VAPID_SERVER_PUBLIC_KEY
npx wrangler secret put VAPID_SERVER_PRIVATE_KEY
npx wrangler secret put TRIGGER_TOKEN
npx wrangler deploy
```
Use a subject such as `mailto:you@example.com`. Generate a VAPID key pair once with a Web Push VAPID generator and keep the private key secret.

## 3. Configure the website

Put the deployed Worker HTTPS URL into the root `push-config.js` as `apiUrl`.

## 4. Configure GitHub Actions

Add repository Actions secrets:
- `PUSH_API_URL` = Worker HTTPS URL
- `PUSH_TRIGGER_TOKEN` = same random trigger token stored in the Worker

The daily workflow will send a push only when the update checker finds new candidates.
