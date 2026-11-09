/*
 * Savings: a Plasma widget for the self-hosted Savings app.
 * Read-only: it shows your numbers and charts. Everything else happens in the website, which
 * "Open Savings" opens in the browser (the browser keeps its own login). Talks to the server over
 * the LAN with a device token (Settings → KDE widget in the app):
 *   GET  /api/summary     what's shown
 * The last summary is kept, so the numbers stay visible (marked offline) when the server
 * can't be reached.
 */
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import org.kde.notification

PlasmoidItem {
    id: root

    readonly property string server: (Plasmoid.configuration.serverUrl || "").trim().replace(/\/+$/, "")
    readonly property string token: (Plasmoid.configuration.token || "").trim()
    readonly property bool configured: server !== "" && token !== ""
    readonly property string version: Plasmoid.metaData.version || "1.0.0"

    property var summary: null          // last good /api/summary
    property bool loading: false
    property bool offline: false        // last refresh failed (summary may be the cached one)
    property string problem: ""         // why, in words
    property date lastOk: new Date(0)

    // the app's colours, following the Plasma theme
    readonly property bool dark: Kirigami.ColorUtils.brightnessForColor(Kirigami.Theme.backgroundColor) === Kirigami.ColorUtils.Dark
    readonly property color good: Kirigami.Theme.positiveTextColor
    readonly property color bad: Kirigami.Theme.negativeTextColor
    readonly property color warn: Kirigami.Theme.neutralTextColor
    readonly property color joint: dark ? "#c7a4f0" : "#6f3fb0"
    // the app's chart colours (themes/light.css and dark.css)
    readonly property var palette: dark
        ? ["#66bb6a", "#64b5f6", "#ffca28", "#ba68c8", "#ff8a65", "#4db6ac", "#e57373", "#b0bec5"]
        : ["#2e7d32", "#1f6fb2", "#d99a00", "#8e44ad", "#d35400", "#16a085", "#c0392b", "#6c7a74"]
    readonly property color chartSpent: dark ? "#e57373" : "#c0504d"
    readonly property color chartIncome: dark ? "#66bb6a" : "#2e7d32"
    readonly property color chartExtra: dark ? "#ffca28" : "#e0a526"

    // appearance (Settings → Appearance)
    readonly property var cfg: Plasmoid.configuration
    readonly property bool privacy: cfg.privacy
    property bool revealed: false        // privacy: amounts shown (hovering the panel / clicked in the popup)
    readonly property int periods: [3, 6, 12].indexOf(cfg.trendPeriods) >= 0 ? cfg.trendPeriods : 6
    onPeriodsChanged: refresh()

    // in a panel: the compact button with a popup; on the desktop (or a window) with enough room:
    // the full view directly
    switchWidth: Kirigami.Units.gridUnit * 16
    switchHeight: Kirigami.Units.gridUnit * 20
    compactRepresentation: CompactRepresentation {}
    fullRepresentation: FullRepresentation {}

    toolTipMainText: summary ? i18n("Savings · %1", summary.period.label) : i18n("Savings")
    toolTipSubText: !configured ? i18n("Not connected yet: open the widget's settings")
                  : summary && pendingInvites > 0 ? i18np("1 invitation waiting · open Savings to answer it", "%1 invitations waiting · open Savings to answer them", pendingInvites)
                  : summary ? i18n("%1 left · %2 a day for %3 days%4", eur(summary.left), eur(summary.per_day),
                                   summary.period.days_left, offline ? i18n(" (offline)") : "")
                  : problem

    Plasmoid.icon: Qt.resolvedUrl("../icons/savings.png")
    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: i18n("Refresh")
            icon.name: "view-refresh"
            onTriggered: root.refresh()
        },
        PlasmaCore.Action {
            text: i18n("Open Savings")
            icon.name: "internet-web-browser"
            enabled: root.server !== ""
            onTriggered: root.openSite("/")
        }
    ]

    // ---------- helpers ----------

    // money as the settings ask: €1,820.30 / €1.820,30, optionally whole euros; "€•••" in privacy mode
    function eur(cents, always) {
        if (cents === null || cents === undefined) return "";
        if (privacy && !revealed && !always) return "€•••";
        var neg = cents < 0, a = Math.abs(Math.round(cents));
        if (cfg.wholeEuros) a = Math.round(a / 100) * 100;
        var eu = cfg.numberFormat === "eu";
        var whole = Math.floor(a / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, eu ? "." : ",");
        var frac = cfg.wholeEuros ? "" : (eu ? "," : ".") + ("0" + (a % 100)).slice(-2);
        return (neg ? "−" : "") + "€" + whole + frac;
    }

    function day(iso) {
        var d = new Date(iso + "T12:00:00");
        return Qt.formatDate(d, "d MMM");
    }

    function request(method, path, body, done) {
        var xhr = new XMLHttpRequest();
        xhr.open(method, root.server + path);
        xhr.setRequestHeader("Authorization", "Bearer " + root.token);
        xhr.setRequestHeader("Accept", "application/json");
        if (body) xhr.setRequestHeader("Content-Type", "application/json");
        xhr.timeout = 10000;
        xhr.onreadystatechange = function () {
            if (xhr.readyState !== XMLHttpRequest.DONE) return;
            var json = null;
            try { json = JSON.parse(xhr.responseText); } catch (e) { json = null; }
            done(xhr.status, json);
        };
        xhr.send(body ? JSON.stringify(body) : null);
    }

    // The server's API generation this widget understands (/api/summary "api"). The server only
    // adds fields within a generation; a new generation means this widget must be updated.
    readonly property int apiVersion: 1

    function refresh() {
        if (!configured) { problem = i18n("Set the server address and a widget token in the widget's settings."); return; }
        if (loading) return;
        loading = true;
        request("GET", "/api/summary?periods=" + periods, null, function (status, json) {
            loading = false;
            if (status === 200 && json && (json.api || 1) > apiVersion) {
                offline = true;               // keep showing the last numbers this widget understood
                problem = i18n("Your Savings server is newer than this widget. Update the widget (Savings → Settings → KDE widget).");
            } else if (status === 200 && json) {
                summary = json;
                offline = false;
                problem = "";
                lastOk = new Date();
                Plasmoid.configuration.cache = JSON.stringify(json);
                processNotifications(json.notifications);
            } else {
                offline = true;
                problem = status === 0 ? i18n("Can't reach the server at %1.", root.server)
                        : status === 401 ? i18n("The token was refused: create a new one in Savings → Settings → KDE widget.")
                        : (json && json.error) ? json.error
                        : i18n("The server answered with an error (%1).", status);
            }
        });
    }

    // "Open Savings": opens the site in the browser (on `path` if given). The browser uses its
    // own login, like any visit; the widget's token is never involved.
    function openSite(path) {
        if (root.server === "") return;
        var target = typeof path === "string" && path.charAt(0) === "/" ? path : "/";
        Qt.openUrlExternally(root.server + target);
        root.expanded = false;
    }

    // ---------- desktop notifications (Settings → Notifications) ----------

    readonly property int pendingInvites: summary && summary.notifications
        ? summary.notifications.filter(function (n) { return n.type === "invite"; }).length : 0
    property var shownNotifications: []     // keep the objects alive until they're closed

    function enabledType(type) {
        return { invite: cfg.notifyInvites, shared: cfg.notifyShared, reset: cfg.notifyReset,
                 recurring: cfg.notifyRecurring, budget: cfg.notifyBudgets }[type] === true;
    }
    // Show each new event once. On the very first check, older events are only marked as seen
    // (pending invitations are still shown: they're waiting for you).
    function processNotifications(list) {
        if (!list) return;
        var seen = (cfg.seenNotifications || "").split(",").filter(function (x) { return x !== ""; });
        var first = !cfg.notificationsPrimed;
        list.forEach(function (n) {
            if (seen.indexOf(n.id) >= 0) return;
            seen.push(n.id);
            if (enabledType(n.type) && (!first || n.type === "invite")) notify(n);
        });
        cfg.seenNotifications = seen.slice(-300).join(",");
        if (first) cfg.notificationsPrimed = true;
    }
    function notify(n) {
        var o = notificationComponent.createObject(root, { title: n.title, text: n.body, target: n.url || "/" });
        if (!o) return;
        shownNotifications = shownNotifications.concat([o]);
        o.sendEvent();
    }
    Component {
        id: notificationComponent
        Notification {
            id: note
            property string target: "/"
            componentName: "plasma_workspace"
            eventId: "notification"
            iconName: Qt.resolvedUrl("../icons/savings.png").toString().replace("file://", "")
            defaultAction: NotificationAction { label: i18n("Open in Savings"); onActivated: root.openSite(target) }
            actions: [ NotificationAction { label: i18n("Open in Savings"); onActivated: root.openSite(target) } ]
            onClosed: root.shownNotifications = root.shownNotifications.filter(function (x) { return x !== note; })
        }
    }

    Component.onCompleted: {
        try {
            if (Plasmoid.configuration.cache) { summary = JSON.parse(Plasmoid.configuration.cache); offline = true; }
        } catch (e) { summary = null; }
        refresh();
    }
    onConfiguredChanged: refresh()
    onServerChanged: refresh()
    onTokenChanged: refresh()
    onExpandedChanged: {
        revealed = false;                 // privacy: the popup starts hidden, and hides again when closed
        if (root.expanded) refresh();
    }

    Timer {
        interval: Math.max(1, Plasmoid.configuration.refreshMinutes) * 60000
        running: root.configured
        repeat: true
        onTriggered: root.refresh()
    }
}
