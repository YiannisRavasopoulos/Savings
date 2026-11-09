# Savings · KDE Plasma widget

A Plasma 6 widget for the self-hosted [Savings](../README.md) app (this folder is part of its repo). It sits in your panel
showing what's left this period, and opens into read-only panels and charts. Anything you want to
*do* (add, edit, plan) happens in the website, which **Open Savings** opens in your browser.

- **Panel:** the Savings icon and what's left (red when over), plus "€75/day" if you like.
  A left click opens the popup, a middle click refreshes.
- **Popup:** two tabs in a toolbar under the header, **Overview** and **Budget**. It opens on the
  one chosen in Appearance → **Open on**.
- **Overview tab:**
  - left over, with the period's progress bar;
  - income, spent and budget used;
  - **Where it went:** a doughnut of this period's spending by category, in the app's colours.
    Future-dated parts are lighter, and shared categories are purple in the legend.
  - **Spent vs income** for the last 6 periods. Spent has future-dated spending lighter on top;
    income is regular, with extra income stacked in amber. Hover a period for its numbers.
  - the budgets closest to their limit, and the last 5 expenses.
- **Budget tab** (savings vs budget, as on the app's Budget page):
  - how far ahead of (green, "saved") or behind (red, "damage") your budgets you are by today, on
    a bar centred on zero, and what you're on track to save this period if you keep to budget;
  - **By category:** each category's balance as a bar from the centre, biggest damage first;
  - **Budget pace:** day-to-day spending against the budget spread evenly over the period, the
    gap shaded green (under) or red (over). Bills, one-offs and future-dated expenses are left out.
  - **Learn how** opens a short explanation with this period's numbers; hover a category for
    its details.
  - Needs a Savings server that sends this data; an older one shows a note instead.
- **Open Savings** (at the bottom of the popup, or right-click → Open Savings): opens the server's
  address in your default browser. That's all it does: the browser uses its own login (its saved
  cookie), like any visit, and asks you to log in if it isn't logged in yet.
- **Offline:** if the server can't be reached, the last numbers stay up and the footer says
  they're from when.

## Notifications (right-click → Configure Savings… → Notifications)

The widget can show normal **Plasma desktop notifications**. Each event notifies you once, and
clicking it (or *Open in Savings*) opens that page of Savings in your browser.

| Event | Default |
|---|---|
| An **invitation** to a shared category | on |
| **Changes in your shared categories**: someone joins, leaves, is removed, shares change, moderation is handed over, the category is closed (only what others did) | on |
| Your **budget period resets** in 3 days | off |
| A **recurring payment** was added | off |
| A category reaches **90 %** or goes **over** its budget | off |

- **Pending invitations** also put a dot on the panel icon, and the popup's button reads "Open
  Savings · 1 invitation" until you've answered in Savings.
- **When it checks:** whenever the widget refreshes (every few minutes, and when you open it).
  Something that happened while the PC was off appears next time.
- **First run:** the first time the widget connects, older events are only marked as seen, so you
  don't get a flood. Pending invitations are still shown.

The popup's header also shows who it's connected as (name · @username).

## Appearance (right-click → Configure Savings… → Appearance)

| Setting | Choices |
|---|---|
| **Panel shows** | what's left (default), left per day, spent this period, budget used (%), or icon only |
| **Panel text** | plain (€1,820), with a word (€1,820 left), or two lines for tall panels |
| **Mini bar** under the number | none, how far through the period, or budget used (turns amber at 85 %, red over 100 %) |
| **Colour the number** | no, red only when over (default), or green / amber / red by budget use |
| **Panel icon** | the Savings logo, monochrome (follows the panel theme), or none |
| **Privacy** | amounts show as €••• until you hover the panel, or click in the popup (or press the eye button). They're hidden again when the popup closes. |
| **Open on** | which popup tab opens first: Overview (default) or Budget. You can always switch with the toolbar. |
| **Popup sections** | tick which show on the Overview tab and move them up or down: Left over, Income · Spent · Budget used, Where it went, Spent vs income, Budgets, Recent |
| **Where it went** | doughnut or horizontal bars |
| **Spent vs income** | the last 3, 6 or 12 periods |
| **Future-dated spending** | shown lighter in the charts, or counted as ordinary spending |
| **Density** | comfortable or compact (smaller numbers, tighter rows, no detail line under recent expenses) |
| **Popup size** | small, medium or large. If you've resized the popup by dragging its edge, Plasma keeps that size instead. |
| **Number format** | €1,820.30 or €1.820,30, optionally whole euros only |

Colours follow the Plasma theme (light or dark) and the app's chart palette.

**After installing a new version**, restart Plasma (`plasmashell --replace & disown`) or log out and
in. A widget that's already running keeps its old code and its old list of settings until then, so
new settings don't save or take effect.

It's a pure QML widget, so there's nothing to compile. It talks to your Savings server over your
LAN with a **device token**. It needs no internet, Docker or Python on the client PC.

## Requirements

- **Client PC:** KDE Plasma 6 (any 6.x) that can reach the Savings server on your network.
- **Building it:** `python3` (standard library only). `kpackagetool6` (part of Plasma) to
  install it from the command line.
- **Server:** Savings with the widget API (schema v15 or later). It only answers the widget's
  requests; it doesn't host the widget.

## Install on any Plasma PC

The widget is a client-side package: get its release once, then copy it to each PC (USB stick,
network share, scp…). The Savings server doesn't host or distribute it, and the Savings release
doesn't include it: the widget has its own releases and version, so it can be updated on its own.

1. Get `savings-widget-<version>.tar.gz` (and its `.sha256`) from the **Releases** page.
2. On each PC: `tar xf savings-widget-<version>.tar.gz && cd savings-widget-<version> && ./install.sh`.
   It installs the widget, or upgrades an older one. The release's `INSTALL.md` explains the rest,
   including installing without a terminal.

   On this PC, `./build-widget.sh --install` does it directly from the source.
3. Add **Savings** to a panel or the desktop.
4. Configure it: right-click it → *Configure Savings…*. Enter the server address (the one you open
   Savings with, e.g. `http://192.168.0.10:8090`) and a **token**. Create the token in Savings →
   Settings → KDE widget; name it after the PC and copy it, since it's shown once.

To remove it, remove the widget from your panels, then run `./uninstall.sh` from the release (or
`kpackagetool6 -t Plasma/Applet -r local.savings.widget`).

## Tokens and privacy

- **What a token can do:** read your own summary, nothing else. It can't add, change or delete
  anything, can't log a browser in, and can't see other people's data.
- **Revoking:** it's listed in Settings → KDE widget, with when it was last used. Revoke it there
  and that widget stops working at once.
- **Storage:** the server keeps only a fingerprint (sha256) of the token. The widget stores it in
  its Plasma config file (`~/.config/plasma-org.kde.plasma.desktop-appletsrc`), readable by your
  user on that PC.
- **No encryption:** traffic is plain HTTP on your LAN, like the app itself.

## Developing

```
package/                 the widget (installed as local.savings.widget)
  metadata.json          id, name, version (bump it for each release)
  contents/ui/           main.qml (data, network, notifications), CompactRepresentation.qml (panel),
                         FullRepresentation.qml (popup: panels and charts),
                         configGeneral / configAppearance / configNotifications.qml (settings pages)
  contents/config/       settings: connection (server, token, refresh) and appearance
build-widget.sh          zip it into dist/, optionally install it here
make-release.sh          builds the release archive (used by the maintainer)
installer/               what the release ships besides the .plasmoid: install.sh, uninstall.sh, INSTALL.md
../.release-denylist     personal words a release must never contain (shared with the app; stays on this PC)
```

- **Use your changes here:** `./build-widget.sh --install`, then restart Plasma.
- **Try it in a window, without touching the panel:** `plasmawindowed local.savings.widget`.

The server side it talks to lives in `../app/api.py`: `/api/summary`.
