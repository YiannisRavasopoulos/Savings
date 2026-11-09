# KDE Plasma widget

[← Savings](../README.md) · [All docs](README.md)

A read-only Plasma 6 widget shows what's left in your panel. It opens into panels and charts:
left over, where it went, spent vs income, budgets and recent expenses. Its **Open Savings**
button opens this website in your browser (which uses its own login), for everything else. It's a **separate client-side
project** in `widget/`, with its own README, packaging and releases. This server only provides the
small API the widget talks to.

- **Connect a widget:** Settings → **KDE widget** → create a **token** named after the PC. It's
  shown once, so copy it into the widget's settings together with the server address. Each token
  is listed with when it was last used, and **Revoke** cuts that widget off at once.
- **Notifications:** the summary also lists recent events the widget can show as Plasma desktop
  notifications. These are pending invitations; what others did in your shared categories (last 14
  days); the reset reminder; recurring payments added (last 3 days); and budgets at 90 % or over.
  Each has a stable id, so the widget shows it once, and a page path, which a click opens in the
  browser.
- **Lost a token?** Tokens are shown only once, when created. Revoke the old one and create a new
  one for that PC.
- **What a token can do:** read its owner's summary (`GET /api/summary`, optionally
  `?periods=3|6|12` for the Spent vs income chart), nothing else. It can't change anything or log
  a browser in: **Open Savings** just opens the server's address, and the browser uses its own
  login cookie like any visit. The server stores only hashes of tokens.
