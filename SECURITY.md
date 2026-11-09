# Security

## How Savings is meant to run

Savings is designed for a **home network or a VPN**, not the public internet.

- It serves **plain HTTP**. On your network, passwords and data travel unencrypted, like any
  other local web app without HTTPS. Don't forward its port on your router or put it on a public
  address.
- Logins use salted, hashed passwords (scrypt), session cookies, cross-site request
  blocking and login throttling. New accounts must be approved in the admin app.
- The **admin app** listens only on the PC that runs Savings (`127.0.0.1`).
- The **KDE widget** uses a read-only token that can only read its owner's summary. The server
  stores only a fingerprint (sha256) of each token, and tokens can be revoked in Settings.
- Savings makes **no outbound connections** while running. Docker downloads Python packages and
  Chart.js once, when the image is built.
- Your data stays in one folder on your machine, with daily backups next to it. Anyone who can
  read that folder can read your data, so keep it on a disk only you can access.

If you want to reach it from outside your home, use a VPN to your network rather than exposing
the port.

## Supported versions

Only the latest Savings release and the latest widget release get fixes. Upgrading keeps your
data and settings.

## Reporting a vulnerability

Please **don't open a public issue** for a security problem. Use GitHub's private
**"Report a vulnerability"** button on the repository's **Security** tab, with:

- what the problem is and what an attacker could do with it,
- how to reproduce it (a test copy with made-up data, never real data),
- the Savings (and, if relevant, widget) version.

You'll get a reply as soon as possible. Fixes are released as a new version, and the changelog
credits the reporter unless you'd rather not be named.
