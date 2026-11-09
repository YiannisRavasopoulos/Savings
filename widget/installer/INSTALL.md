# Savings widget: install guide

A KDE Plasma 6 panel widget for **Savings**, the self-hosted spending tracker. It shows what's
left this period and opens into read-only panels and charts. It needs a Savings server that this
PC can reach on your network. It doesn't include the server.

## What you need

- **KDE Plasma 6** (any 6.x).
- A **Savings server** on your network (Savings 1.0.0 or later), and an account on it.
- Nothing else: no Docker, Python or internet on this PC.

## Install

```sh
tar xf savings-widget-<version>.tar.gz
cd savings-widget-<version>
./install.sh
```

It installs the widget for your user (no sudo). If an older version is installed, it upgrades it
and keeps your settings.

Without a terminal: right-click the desktop → *Add or Manage Widgets…* → *Get New* → **Install
Widget From Local File…**, and pick `savings-<version>.plasmoid`.

## Set it up

1. Right-click the panel → *Add or Manage Widgets…* → drag **Savings** to the panel.
2. In Savings (in your browser) → Settings → **KDE widget**, create a token. Name it after this
   PC and copy it: it's shown only once.
3. Right-click the widget → *Configure Savings…*. Enter the server address (the one you open
   Savings with, e.g. `http://192.168.0.10:8090`) and the token.

## Upgrade

Run `./install.sh` from the newer version. Then restart Plasma once
(`plasmashell --replace & disown`, or log out and in): a running widget keeps its old version
until then.

It won't replace a newer installed widget with an older one; `./install.sh --force` does that on
purpose. If the widget ever says "Your Savings server is newer than this widget", install the
newest widget release.

## Remove

Remove the widget from your panels, then run `./uninstall.sh`. Revoke its token in Savings →
Settings → KDE widget.

## Privacy

The token can only read your own summary. It can't change anything or see anyone else's data.
The widget talks only to your Savings server, over your network.
