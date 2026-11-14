// The popup: read-only panels and charts, plus "Open Savings" (opens the site in the browser)
// for everything else. Two tabs: Overview (the sections) and Budget (savings vs budget). Which
// tab it opens on, which sections show, their order, density, size and chart styles come from
// Settings → Appearance.
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PC3
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami

PlasmaExtras.Representation {
    id: full

    readonly property var s: root.summary
    readonly property var cfg: Plasmoid.configuration
    readonly property bool compact: cfg.density === "compact"
    readonly property real gap: compact ? Kirigami.Units.smallSpacing : Kirigami.Units.largeSpacing
    readonly property bool showFuture: cfg.showFuture
    readonly property real sizeFactor: cfg.popupSize === "small" ? 0.85 : cfg.popupSize === "large" ? 1.25 : 1

    readonly property var allSections: ["left", "stats", "where", "trend", "budgets", "recent"]
    readonly property var order: {
        var saved = (cfg.sections || "").split(",").filter(function (n) { return allSections.indexOf(n) >= 0; });
        var hidden = (cfg.hiddenSections || "").split(",");
        return saved.concat(allSections.filter(function (n) { return saved.indexOf(n) < 0; }))
                    .filter(function (n) { return hidden.indexOf(n) < 0; });
    }
    readonly property var components: ({ left: secLeft, stats: secStats, where: secWhere, trend: secTrend,
                                         budgets: secBudgets, recent: secRecent })

    // tabs: the popup opens on the one chosen in Settings → Appearance ("Open on")
    readonly property string primary: cfg.primaryTab === "budget" ? "budget" : "overview"
    property string tab: primary
    onPrimaryChanged: tab = primary
    onTabChanged: tabs.currentIndex = tab === "budget" ? 1 : 0
    readonly property bool ready: root.configured && full.s !== null
    readonly property var vb: s && s.vs_budget ? s.vs_budget : null    // null: a server without it
    Connections {
        target: root
        function onExpandedChanged() { if (root.expanded) full.tab = full.primary; }
    }

    Layout.minimumWidth: Kirigami.Units.gridUnit * 18
    Layout.preferredWidth: Kirigami.Units.gridUnit * 23 * sizeFactor
    Layout.minimumHeight: Kirigami.Units.gridUnit * 20
    Layout.preferredHeight: Kirigami.Units.gridUnit * 36 * sizeFactor
    collapseMarginsHint: true

    header: PlasmaExtras.PlasmoidHeading {
      ColumnLayout {
        anchors.fill: parent
        spacing: Kirigami.Units.smallSpacing
        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing
            ColumnLayout {
                spacing: 0
                Layout.fillWidth: true
                PC3.Label {   // who this is
                    visible: full.s !== null && !!full.s.username
                    text: full.s ? (full.s.user && full.s.user !== full.s.username ? full.s.user + " · " : "") + "@" + full.s.username : ""
                    font: Kirigami.Theme.smallFont
                    opacity: 0.75
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                Kirigami.Heading {
                    level: 3
                    text: full.s ? full.s.period.label : i18n("Savings")
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                PC3.Label {
                    visible: full.s !== null
                    text: full.s ? full.s.period.range : ""
                    font: Kirigami.Theme.smallFont
                    opacity: 0.7
                }
            }
            PC3.BusyIndicator {
                visible: root.loading
                running: visible
                Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                Layout.preferredHeight: Layout.preferredWidth
            }
            PC3.ToolButton {
                visible: root.privacy
                icon.name: root.revealed ? "view-hidden" : "view-visible"
                onClicked: root.revealed = !root.revealed
                PC3.ToolTip.text: root.revealed ? i18n("Hide amounts") : i18n("Show amounts")
                PC3.ToolTip.visible: hovered
            }
            PC3.ToolButton {
                icon.name: "view-refresh"
                onClicked: root.refresh()
                visible: root.configured
                PC3.ToolTip.text: i18n("Refresh")
                PC3.ToolTip.visible: hovered
            }
            PC3.ToolButton {
                icon.name: "configure"
                onClicked: Plasmoid.internalAction("configure").trigger()
                PC3.ToolTip.text: i18n("Widget settings")
                PC3.ToolTip.visible: hovered
            }
        }
        PC3.TabBar {   // the toolbar: Overview | Budget
            id: tabs
            Layout.fillWidth: true
            visible: full.ready
            Component.onCompleted: currentIndex = full.tab === "budget" ? 1 : 0
            PC3.TabButton {
                text: i18n("Overview")
                icon.name: "view-list-details"
                onClicked: full.tab = "overview"
            }
            PC3.TabButton {
                text: i18n("Budget")
                icon.name: "office-chart-line"
                onClicked: full.tab = "budget"
            }
        }
      }
    }

    footer: PlasmaExtras.PlasmoidHeading {
        position: PC3.ToolBar.Footer
        visible: root.server !== ""
        PC3.Button {
            anchors.fill: parent
            text: root.pendingInvites > 0 ? i18np("Open Savings · 1 invitation", "Open Savings · %1 invitations", root.pendingInvites)
                                          : i18n("Open Savings")
            onClicked: root.openSite("/")
            PC3.ToolTip.text: i18n("Opens Savings in your browser, to add or change anything")
            PC3.ToolTip.visible: hovered
        }
    }

    // ---------- not connected yet ----------
    ColumnLayout {
        anchors.centerIn: parent
        width: parent.width - Kirigami.Units.gridUnit * 2
        visible: !root.configured || (full.s === null && root.problem !== "")
        spacing: Kirigami.Units.largeSpacing
        Kirigami.Icon {
            source: Qt.resolvedUrl("../icons/savings.png")
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: Kirigami.Units.iconSizes.huge
            Layout.preferredHeight: Layout.preferredWidth
        }
        PC3.Label {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: !root.configured ? i18n("Connect the widget to your Savings server: create a token in Savings → Settings → KDE widget, then enter it with the server address here.")
                                   : root.problem
        }
        PC3.Button {
            Layout.alignment: Qt.AlignHCenter
            icon.name: "configure"
            text: root.configured ? i18n("Check settings") : i18n("Connect…")
            onClicked: Plasmoid.internalAction("configure").trigger()
        }
        PC3.Button {
            Layout.alignment: Qt.AlignHCenter
            visible: root.configured
            icon.name: "view-refresh"
            text: i18n("Try again")
            onClicked: root.refresh()
        }
    }

    // ---------- the sections, in the chosen order ----------
    PC3.ScrollView {
        id: scroll
        anchors.fill: parent
        visible: full.ready && full.tab === "overview"
        contentWidth: availableWidth
        QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

        ColumnLayout {
            width: scroll.availableWidth
            spacing: full.gap

            Item { Layout.preferredHeight: 1 }
            Repeater {
                model: full.order
                Loader {
                    required property string modelData
                    Layout.fillWidth: true
                    sourceComponent: full.components[modelData]
                    visible: item !== null && item.show
                }
            }
            Loader { Layout.fillWidth: true; sourceComponent: statusLine }
        }
    }

    // ---------- the Budget tab: savings vs budget, by category, pace ----------
    PC3.ScrollView {
        id: budgetScroll
        anchors.fill: parent
        visible: full.ready && full.tab === "budget"
        contentWidth: availableWidth
        QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

        ColumnLayout {
            width: budgetScroll.availableWidth
            spacing: full.gap

            Item { Layout.preferredHeight: 1 }
            PC3.Label {
                visible: full.vb === null || full.vb.budget <= 0
                Layout.fillWidth: true
                Layout.topMargin: Kirigami.Units.largeSpacing
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                opacity: 0.8
                text: full.vb === null ? i18n("Update your Savings server to see savings vs budget here.")
                                       : i18n("Set budgets on your categories in Savings to see how much you're saving or losing against them.")
            }
            Loader { Layout.fillWidth: true; active: full.vb !== null && full.vb.budget > 0; visible: active; sourceComponent: secGauge }
            Loader { Layout.fillWidth: true; active: full.vb !== null && full.vb.budget > 0; visible: active; sourceComponent: secBalanceCats }
            Loader { Layout.fillWidth: true; active: full.vb !== null && full.vb.budget > 0; visible: active; sourceComponent: secPace }
            Loader { Layout.fillWidth: true; sourceComponent: statusLine }
        }
    }

    Component {
        id: statusLine
        PC3.Label {
            Layout.bottomMargin: Kirigami.Units.smallSpacing
            wrapMode: Text.WordWrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: root.offline
                  ? i18n("Offline. %1", root.problem) + (full.s && full.s.updated_at ? " " + i18n("Numbers from %1.", Qt.formatDateTime(new Date(full.s.updated_at), "d MMM hh:mm")) : "")
                  : i18n("Updated %1.", Qt.formatTime(root.lastOk, "hh:mm"))
        }
    }

    // privacy: a click anywhere in the popup shows the amounts
    MouseArea {
        anchors.fill: parent
        visible: root.privacy && !root.revealed && full.s !== null
        z: 20
        onClicked: root.revealed = true
        cursorShape: Qt.PointingHandCursor
    }

    // ---------- sections ----------

    Component {
        id: secLeft
        ColumnLayout {
            readonly property bool show: full.s !== null
            spacing: Kirigami.Units.smallSpacing
            PC3.Label { text: i18n("Left over"); opacity: 0.7 }
            PC3.Label {
                property real shown: full.s ? full.s.left : 0
                text: root.eur(shown)
                font.pixelSize: Kirigami.Units.gridUnit * (full.compact ? 1.7 : 2.2)
                font.bold: true
                color: full.s && full.s.left < 0 ? root.bad : Kirigami.Theme.textColor
                Behavior on shown { NumberAnimation { duration: 750; easing.type: Easing.OutCubic } }
            }
            PC3.Label {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                opacity: 0.8
                text: !full.s ? ""
                    : full.s.left > 0 ? i18np("%2 a day for the last day", "%2 a day for the %1 days left", full.s.period.days_left, root.eur(full.s.per_day))
                    : full.s.left < 0 ? i18np("Over by %2 with %1 day left", "Over by %2 with %1 days left", full.s.period.days_left, root.eur(-full.s.left))
                    : i18np("%1 day left", "%1 days left", full.s.period.days_left)
            }
            Rectangle {   // the period's progress
                Layout.fillWidth: true
                height: 6
                radius: 3
                color: Qt.alpha(Kirigami.Theme.textColor, 0.12)
                Rectangle {
                    width: full.s ? parent.width * full.s.period.day / full.s.period.days_total : 0
                    height: parent.height
                    radius: 3
                    color: root.good
                }
            }
        }
    }

    Component {
        id: secStats
        RowLayout {
            readonly property bool show: full.s !== null
            spacing: Kirigami.Units.largeSpacing
            Repeater {
                model: full.s ? [
                    { label: i18n("Income"), value: root.eur(full.s.income), tone: "" },
                    { label: i18n("Spent"), value: root.eur(full.s.spent), tone: "" },
                    { label: i18n("Budget used"), value: full.s.budget_pct === null ? "–" : Math.round(full.s.budget_pct) + "%",
                      tone: full.s.budget_pct === null ? "" : full.s.budget_pct > 100 ? "bad" : full.s.budget_pct >= 85 ? "warn" : "" }
                ] : []
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 0
                    PC3.Label { text: modelData.label; font: Kirigami.Theme.smallFont; opacity: 0.7 }
                    PC3.Label {
                        text: modelData.value
                        font.bold: true
                        color: modelData.tone === "bad" ? root.bad : modelData.tone === "warn" ? root.warn : Kirigami.Theme.textColor
                    }
                }
            }
        }
    }

    // where it went: a doughnut + legend, or horizontal bars (future-dated parts lighter)
    Component {
        id: secWhere
        ColumnLayout {
            id: where
            readonly property var cats: full.s && full.s.charts ? full.s.charts.categories : []
            readonly property bool show: cats.length > 0
            readonly property real maxSpent: cats.length ? cats[0].spent : 1
            function past(c) { return full.showFuture ? c.spent - c.future : c.spent; }
            function fut(c) { return full.showFuture ? c.future : 0; }
            spacing: Kirigami.Units.smallSpacing
            Kirigami.Heading { level: 4; text: i18n("Where it went") }

            RowLayout {
                visible: full.cfg.whereChart !== "bars"
                Layout.fillWidth: true
                spacing: Kirigami.Units.largeSpacing
                Canvas {
                    id: doughnut
                    Layout.preferredWidth: Kirigami.Units.gridUnit * (full.compact ? 6 : 7.5)
                    Layout.preferredHeight: Layout.preferredWidth
                    readonly property var deps: [where.cats, root.dark, full.showFuture]
                    onDepsChanged: requestPaint()
                    onPaint: {
                        var ctx = getContext("2d");
                        ctx.reset();
                        var cats = where.cats, total = 0;
                        for (var i = 0; i < cats.length; i++) total += cats[i].spent;
                        if (total <= 0) return;
                        var r = width / 2, lw = r * 0.36, a = -Math.PI / 2;
                        ctx.lineWidth = lw;
                        for (var j = 0; j < cats.length; j++) {
                            var c = cats[j], col = root.palette[j % root.palette.length];
                            var parts = [[where.past(c), 1], [where.fut(c), 0.35]];
                            for (var k = 0; k < 2; k++) {
                                if (parts[k][0] <= 0) continue;
                                var sweep = parts[k][0] / total * Math.PI * 2;
                                ctx.globalAlpha = parts[k][1];
                                ctx.strokeStyle = col;
                                ctx.beginPath();
                                ctx.arc(r, r, r - lw / 2, a, a + sweep - 0.015);
                                ctx.stroke();
                                a += sweep;
                            }
                        }
                        ctx.globalAlpha = 1;
                    }
                    PC3.Label {
                        anchors.centerIn: parent
                        text: full.s ? root.eur(full.s.spent) : ""
                        font.bold: true
                        font.pixelSize: Kirigami.Theme.smallFont.pixelSize * 1.1
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 2
                    Repeater {
                        model: where.cats.slice(0, 8)
                        RowLayout {
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            Rectangle { width: 10; height: 10; radius: 2; color: root.palette[index % root.palette.length] }
                            PC3.Label {
                                text: modelData.name
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font: Kirigami.Theme.smallFont
                                color: modelData.joint ? root.joint : Kirigami.Theme.textColor
                            }
                            PC3.Label { text: root.eur(modelData.spent); font: Kirigami.Theme.smallFont; opacity: 0.85 }
                        }
                    }
                }
            }

            ColumnLayout {   // bars
                visible: full.cfg.whereChart === "bars"
                Layout.fillWidth: true
                spacing: full.compact ? 2 : 4
                Repeater {
                    model: where.cats
                    ColumnLayout {
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        spacing: 1
                        RowLayout {
                            Layout.fillWidth: true
                            PC3.Label {
                                text: modelData.name
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font: Kirigami.Theme.smallFont
                                color: modelData.joint ? root.joint : Kirigami.Theme.textColor
                            }
                            PC3.Label { text: root.eur(modelData.spent); font: Kirigami.Theme.smallFont; opacity: 0.85 }
                        }
                        Item {
                            Layout.fillWidth: true
                            height: full.compact ? 6 : 8
                            readonly property color col: root.palette[index % root.palette.length]
                            readonly property real unit: width / where.maxSpent
                            Rectangle { width: where.past(modelData) * parent.unit; height: parent.height; radius: 2; color: parent.col }
                            Rectangle { x: where.past(modelData) * parent.unit; width: where.fut(modelData) * parent.unit; height: parent.height
                                radius: 2; color: Qt.alpha(parent.col, 0.3); border.color: parent.col; border.width: where.fut(modelData) > 0 ? 1 : 0 }
                        }
                    }
                }
            }
        }
    }

    // spent vs income per period
    Component {
        id: secTrend
        ColumnLayout {
            id: trend
            readonly property var t: full.s && full.s.charts ? full.s.charts.trend : null
            readonly property bool show: t !== null
            function n(v) { return v === null || v === undefined ? 0 : v; }
            readonly property real maxV: {
                if (!t) return 1;
                var m = 1;
                for (var i = 0; i < t.labels.length; i++)
                    m = Math.max(m, n(t.spent_past[i]) + n(t.spent_future[i]), n(t.regular[i]) + n(t.extra[i]));
                return m;
            }
            readonly property bool anyFuture: full.showFuture && t ? t.spent_future.some(function (v) { return v > 0; }) : false
            readonly property bool anyExtra: t ? t.extra.some(function (v) { return v > 0; }) : false
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Heading { level: 4; text: i18np("Spent vs income, last period", "Spent vs income, last %1 periods", trend.t ? trend.t.labels.length : 0) }
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: Kirigami.Units.gridUnit * (full.compact ? 5.5 : 7)
                spacing: trend.t && trend.t.labels.length > 6 ? 2 : Kirigami.Units.smallSpacing
                Repeater {
                    model: trend.t ? trend.t.labels.length : 0
                    ColumnLayout {
                        required property int index
                        // future-dated spending hidden: counted as ordinary spending
                        readonly property real past: trend.n(trend.t.spent_past[index]) + (full.showFuture ? 0 : trend.n(trend.t.spent_future[index]))
                        readonly property real fut: full.showFuture ? trend.n(trend.t.spent_future[index]) : 0
                        readonly property real reg: trend.n(trend.t.regular[index])
                        readonly property real ext: trend.n(trend.t.extra[index])
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 2
                        Item {
                            id: bars
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            readonly property real unit: height / trend.maxV
                            readonly property real bw: Math.max(2, Math.min(width / 2 - 1, Kirigami.Units.gridUnit * 0.9))
                            Rectangle { x: bars.width / 2 - bars.bw - 1; width: bars.bw; height: past * bars.unit; anchors.bottom: parent.bottom; color: root.chartSpent; radius: 2 }
                            Rectangle { x: bars.width / 2 - bars.bw - 1; width: bars.bw; height: fut * bars.unit; y: bars.height - (past + fut) * bars.unit
                                color: Qt.alpha(root.chartSpent, 0.3); border.color: root.chartSpent; border.width: fut > 0 ? 1 : 0; radius: 2 }
                            Rectangle { x: bars.width / 2 + 1; width: bars.bw; height: reg * bars.unit; anchors.bottom: parent.bottom; color: root.chartIncome; radius: 2 }
                            Rectangle { x: bars.width / 2 + 1; width: bars.bw; height: ext * bars.unit; y: bars.height - (reg + ext) * bars.unit; color: root.chartExtra; radius: 2 }
                            HoverHandler { id: hover }
                            PC3.ToolTip {
                                visible: hover.hovered
                                text: trend.t.labels[index] + "\n" + i18n("Spent: %1", root.eur(Math.round((past + fut) * 100)))
                                      + (fut > 0 ? " " + i18n("(%1 future-dated)", root.eur(Math.round(fut * 100))) : "")
                                      + "\n" + i18n("Income: %1", root.eur(Math.round((reg + ext) * 100)))
                                      + (ext > 0 ? " " + i18n("(%1 extra)", root.eur(Math.round(ext * 100))) : "")
                            }
                        }
                        PC3.Label {
                            Layout.alignment: Qt.AlignHCenter
                            text: trend.t.labels[index]
                            font: Kirigami.Theme.smallFont
                            opacity: 0.7
                            visible: trend.t.labels.length <= 6 || index % 2 === trend.t.labels.length % 2   // every other label at 12
                        }
                    }
                }
            }
            Flow {
                Layout.fillWidth: true
                spacing: Kirigami.Units.largeSpacing
                Repeater {
                    model: [
                        { label: i18n("Spent"), color: root.chartSpent, show: true, faded: false },
                        { label: i18n("Future-dated"), color: root.chartSpent, show: trend.anyFuture, faded: true },
                        { label: i18n("Regular income"), color: root.chartIncome, show: true, faded: false },
                        { label: i18n("Extra income"), color: root.chartExtra, show: trend.anyExtra, faded: false }
                    ]
                    RowLayout {
                        required property var modelData
                        visible: modelData.show
                        spacing: 4
                        Rectangle { width: 10; height: 10; radius: 2; color: modelData.faded ? Qt.alpha(modelData.color, 0.3) : modelData.color
                            border.color: modelData.color; border.width: modelData.faded ? 1 : 0 }
                        PC3.Label { text: modelData.label; font: Kirigami.Theme.smallFont; opacity: 0.8 }
                    }
                }
            }
        }
    }

    Component {
        id: secBudgets
        ColumnLayout {
            readonly property bool show: full.s !== null && full.s.budgets.length > 0
            spacing: Kirigami.Units.smallSpacing
            Kirigami.Heading { level: 4; text: i18n("Budgets") }
            Repeater {
                model: full.s ? full.s.budgets : []
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 2
                    RowLayout {
                        Layout.fillWidth: true
                        PC3.Label {
                            text: modelData.name
                            color: modelData.joint ? root.joint : Kirigami.Theme.textColor
                            font.bold: modelData.joint
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                        PC3.Label {
                            text: i18n("%1 of %2", root.eur(modelData.spent), root.eur(modelData.budget))
                            font: Kirigami.Theme.smallFont
                            opacity: 0.8
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        height: 5
                        radius: 2.5
                        color: Qt.alpha(Kirigami.Theme.textColor, 0.12)
                        Rectangle {
                            width: parent.width * Math.min(1, (modelData.pct || 0) / 100)
                            height: parent.height
                            radius: 2.5
                            color: modelData.status === "red" ? root.bad : modelData.status === "amber" ? root.warn : root.good
                        }
                    }
                }
            }
        }
    }

    Component {
        id: secRecent
        ColumnLayout {
            readonly property bool show: full.s !== null && full.s.recent.length > 0
            spacing: full.compact ? 2 : Kirigami.Units.smallSpacing
            Kirigami.Heading { level: 4; text: i18n("Recent") }
            Repeater {
                model: full.s ? full.s.recent : []
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 0
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        PC3.Label { text: modelData.description; elide: Text.ElideRight; Layout.fillWidth: true }
                        PC3.Label {
                            visible: modelData.future
                            text: i18n("future")
                            font.italic: true
                            font.pixelSize: Kirigami.Theme.smallFont.pixelSize
                            opacity: 0.7
                        }
                        PC3.Label { text: root.eur(modelData.cents); font.bold: true; opacity: modelData.future ? 0.6 : 1 }
                    }
                    PC3.Label {
                        visible: !full.compact
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        font: Kirigami.Theme.smallFont
                        opacity: 0.7
                        color: modelData.joint ? root.joint : Kirigami.Theme.textColor
                        text: modelData.category + " · " + root.day(modelData.date)
                              + (modelData.joint ? " · " + i18n("paid by %1", modelData.mine ? i18n("you") : modelData.paid_by) : "")
                    }
                }
            }
        }
    }

    // ---------- Budget tab sections ----------

    function signed(cents) { return (cents > 0 ? "+" : "") + root.eur(cents); }

    // a bar centred on zero: green to the right (saved), red to the left (damage)
    component Diverging: Rectangle {
        property real value: 0       // cents
        property real range: 1       // cents for a half-width bar
        radius: height / 2
        color: Qt.alpha(Kirigami.Theme.textColor, 0.12)
        Rectangle {
            readonly property real w: parent.width / 2 * Math.min(1, Math.abs(parent.value) / Math.max(1, parent.range))
            x: parent.value >= 0 ? parent.width / 2 : parent.width / 2 - w
            width: w
            height: parent.height
            radius: parent.radius
            color: parent.value >= 0 ? root.good : root.bad
        }
        Rectangle { x: parent.width / 2 - 1; width: 2; height: parent.height; color: Kirigami.Theme.textColor; opacity: 0.5 }
    }

    Component {
        id: secGauge
        ColumnLayout {
            readonly property var vb: full.vb
            spacing: Kirigami.Units.smallSpacing
            Kirigami.Heading { level: 4; text: i18n("Savings vs budget") }
            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                PC3.Label {
                    text: full.signed(vb.balance)
                    font.pixelSize: Kirigami.Units.gridUnit * (full.compact ? 1.5 : 1.9)
                    font.bold: true
                    color: vb.balance >= 0 ? root.good : root.bad
                }
                PC3.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    opacity: 0.75
                    text: vb.balance > 0 ? i18n("saved so far, ahead of budget")
                        : vb.balance < 0 ? i18n("damage so far, behind budget") : i18n("exactly on budget")
                }
            }
            Diverging {
                Layout.fillWidth: true
                height: full.compact ? 8 : 12
                value: vb.balance
                range: Math.max(vb.allowed, Math.abs(vb.balance))
            }
            RowLayout {
                Layout.fillWidth: true
                PC3.Label { text: i18n("damage"); font: Kirigami.Theme.smallFont; opacity: 0.6; Layout.fillWidth: true }
                PC3.Label { text: i18n("saved"); font: Kirigami.Theme.smallFont; opacity: 0.6 }
            }
            PC3.Label {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                textFormat: Text.StyledText
                text: i18n("On track to save <b><font color=\"%1\">%2</font></b> this period if you keep to budget from here.",
                           vb.projected >= 0 ? root.good : root.bad, root.eur(vb.projected))
            }
            PC3.ToolButton {   // the explanation stays out of the way until asked for
                id: learn
                checkable: true
                text: i18n("Learn how")
                icon.name: checked ? "go-up" : "help-about"
                font: Kirigami.Theme.smallFont
            }
            PC3.Label {
                visible: learn.checked
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                textFormat: Text.StyledText
                font: Kirigami.Theme.smallFont
                opacity: 0.85
                text: i18n("Your budgets are spread evenly over the period, so by today (day %1 of %2) they allow <b>%3</b> of day-to-day spending. You've spent <b>%4</b>. Less than that is saved; more is damage.",
                           vb.day, vb.days, root.eur(vb.allowed), root.eur(vb.daily))
                      + "<br>• " + i18n("Bills, one-offs and future-dated expenses don't set the pace: they come off their category's budget straight away. Only the part beyond the budget is damage.")
                      + "<br>• " + i18n("Spending in a category without a budget is all damage.")
                      + "<br>• " + i18n("On track to save = income − spent so far − the rest of your day-to-day budget. Spending exactly your budgets would save %1.", root.eur(vb.planned))
                      + "<br>• " + (vb.pace.spent !== undefined
                         ? i18n("Budget pace shows it day by day: each day has the daily rate plus what carried over from the days before. Bars are red on days above the rate.")
                         : i18n("Budget pace draws the same comparison day by day: green under the dashed line, red over."))
            }
        }
    }

    Component {
        id: secBalanceCats
        ColumnLayout {
            id: balCats
            readonly property var cats: full.vb.categories
            readonly property real maxAbs: cats.reduce(function (m, c) { return Math.max(m, Math.abs(c.balance)); }, 1)
            spacing: full.compact ? 2 : Kirigami.Units.smallSpacing
            Kirigami.Heading { level: 4; text: i18n("By category") }
            Repeater {
                model: balCats.cats
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 2
                    RowLayout {
                        Layout.fillWidth: true
                        PC3.Label {
                            text: modelData.name
                            color: modelData.joint ? root.joint : Kirigami.Theme.textColor
                            font.bold: true
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                        PC3.Label {
                            text: full.signed(modelData.balance)
                            font.bold: true
                            color: modelData.balance >= 0 ? root.good : root.bad
                        }
                    }
                    Diverging {
                        Layout.fillWidth: true
                        height: full.compact ? 5 : 6
                        value: modelData.balance
                        range: balCats.maxAbs
                    }
                    HoverHandler { id: catHover }
                    PC3.ToolTip {
                        visible: catHover.hovered
                        text: modelData.budget <= 0 ? i18n("No budget · %1 spent", root.eur(modelData.spent))
                              : i18n("Allowed %1 by today · spent %2", root.eur(modelData.allowed), root.eur(modelData.daily))
                                + (modelData.fixed > 0 ? " " + i18n("+ %1 bills & one-offs", root.eur(modelData.fixed)) : "")
                    }
                }
            }
        }
    }

    // Budget pace. Savings 1.6.0+: each day's day-to-day spending (bars, red above the daily rate)
    // against what that day had available (step line: the rate plus what carried over), dashed:
    // the rate. Older servers send only actual/allowed: the cumulative chart, as before.
    Component {
        id: secPace
        ColumnLayout {
            id: pace
            readonly property var p: full.vb.pace
            readonly property bool daily: p.spent !== undefined && p.available !== undefined
            readonly property int last: {
                var src = daily ? p.spent : p.actual, l = -1;
                for (var i = 0; i < src.length; i++) if (src[i] !== null && src[i] !== undefined) l = i;
                return l;
            }
            readonly property real maxV: {
                var m = 1, i;
                if (daily) {
                    m = Math.max(m, p.rate || 0);
                    for (i = 0; i <= last; i++) m = Math.max(m, p.spent[i] || 0, p.available[i] || 0);
                } else {
                    for (i = 0; i < p.allowed.length; i++) m = Math.max(m, p.allowed[i], p.actual[i] || 0);
                }
                return m * 1.08;
            }
            spacing: Kirigami.Units.smallSpacing
            Kirigami.Heading { level: 4; text: i18n("Budget pace") }
            Canvas {
                id: paceCanvas
                Layout.fillWidth: true
                Layout.preferredHeight: Kirigami.Units.gridUnit * (full.compact ? 6 : 8)
                readonly property var deps: [pace.p, root.dark, width, height]
                onDepsChanged: requestPaint()
                onPaint: {
                    var ctx = getContext("2d");
                    ctx.reset();
                    function Y(v) { return height - 1 - Math.max(0, v) / pace.maxV * (height - 2); }
                    if (pace.daily) {
                        var s = pace.p.spent, av = pace.p.available, n = s.length;
                        if (n < 1) return;
                        var slot = (width - 2) / n, bw = Math.max(1, slot * 0.7);
                        var L = function (i) { return 1 + i * slot; };
                        // bars: what you spent each day, red above the daily rate
                        for (var i = 0; i <= pace.last; i++) {
                            if (!s[i]) continue;
                            ctx.fillStyle = Qt.alpha(s[i] > pace.p.rate ? root.bad : root.good, 0.8);
                            ctx.fillRect(L(i) + (slot - bw) / 2, Y(s[i]), bw, height - 1 - Y(s[i]));
                        }
                        // the daily rate: dashed
                        ctx.strokeStyle = Qt.alpha(Kirigami.Theme.textColor, 0.55);
                        ctx.lineWidth = 1.25;
                        ctx.setLineDash([5, 4]);
                        ctx.beginPath(); ctx.moveTo(1, Y(pace.p.rate)); ctx.lineTo(width - 1, Y(pace.p.rate)); ctx.stroke();
                        // available that day: a step per day, to today
                        ctx.setLineDash([]);
                        ctx.strokeStyle = Kirigami.Theme.textColor;
                        ctx.lineWidth = 2;
                        ctx.beginPath();
                        for (var k = 0; k <= pace.last; k++) {
                            if (k === 0) ctx.moveTo(L(0), Y(av[0])); else ctx.lineTo(L(k), Y(av[k]));
                            ctx.lineTo(L(k + 1), Y(av[k]));
                        }
                        ctx.stroke();
                        return;
                    }
                    var a = pace.p.actual, b = pace.p.allowed, nn = b.length;
                    if (nn < 2) return;
                    var X = function (i) { return i / (nn - 1) * (width - 2) + 1; };
                    // the gap, day by day: red above the allowance, green below
                    for (var j = 0; j < pace.last; j++) {
                        var over = a[j] > b[j];
                        ctx.fillStyle = Qt.alpha(over ? root.bad : root.good, 0.3);
                        ctx.beginPath();
                        ctx.moveTo(X(j), Y(a[j])); ctx.lineTo(X(j + 1), Y(a[j]));
                        ctx.lineTo(X(j + 1), Y(b[j + 1])); ctx.lineTo(X(j), Y(b[j]));
                        ctx.closePath(); ctx.fill();
                    }
                    ctx.strokeStyle = Qt.alpha(Kirigami.Theme.textColor, 0.55);
                    ctx.lineWidth = 1.5;
                    ctx.setLineDash([5, 4]);
                    ctx.beginPath(); ctx.moveTo(X(0), Y(b[0]));
                    for (var q = 1; q < nn; q++) ctx.lineTo(X(q), Y(b[q]));
                    ctx.stroke();
                    ctx.setLineDash([]);
                    ctx.strokeStyle = Kirigami.Theme.textColor;
                    ctx.lineWidth = 2;
                    ctx.beginPath(); ctx.moveTo(X(0), Y(a[0]));
                    for (var m = 1; m <= pace.last; m++) { ctx.lineTo(X(m), Y(a[m - 1])); ctx.lineTo(X(m), Y(a[m])); }
                    ctx.stroke();
                }
                PC3.Label {   // scale: the top of the chart
                    anchors.left: parent.left
                    anchors.top: parent.top
                    text: root.eur(Math.round(pace.maxV * 100))
                    font: Kirigami.Theme.smallFont
                    opacity: 0.6
                }
            }
            RowLayout {
                Layout.fillWidth: true
                PC3.Label { text: i18n("Day 1"); font: Kirigami.Theme.smallFont; opacity: 0.6; Layout.fillWidth: true }
                PC3.Label { text: i18n("Day %1", full.vb.days); font: Kirigami.Theme.smallFont; opacity: 0.6 }
            }
            Flow {
                Layout.fillWidth: true
                spacing: Kirigami.Units.largeSpacing
                RowLayout {
                    visible: pace.daily
                    spacing: 4
                    Rectangle { width: 10; height: 10; color: Qt.alpha(root.good, 0.8) }
                    Rectangle { width: 10; height: 10; color: Qt.alpha(root.bad, 0.8) }
                    PC3.Label { text: i18n("Spent that day"); font: Kirigami.Theme.smallFont; opacity: 0.8 }
                }
                RowLayout {
                    spacing: 4
                    Rectangle { width: 14; height: 2; color: Kirigami.Theme.textColor }
                    PC3.Label { text: pace.daily ? i18n("Available that day") : i18n("Day-to-day spending"); font: Kirigami.Theme.smallFont; opacity: 0.8 }
                }
                RowLayout {
                    spacing: 4
                    Rectangle { width: 14; height: 2; color: Qt.alpha(Kirigami.Theme.textColor, 0.55) }
                    PC3.Label { text: pace.daily ? i18n("Daily rate (%1)", root.eur(Math.round(pace.p.rate * 100))) : i18n("Allowed by budget"); font: Kirigami.Theme.smallFont; opacity: 0.8 }
                }
            }
        }
    }
}
