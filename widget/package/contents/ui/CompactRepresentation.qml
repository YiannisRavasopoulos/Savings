// In the panel: an icon and a number, as Settings → Appearance asks. Click to open, middle click
// to refresh. In privacy mode the amounts show as €••• until you hover.
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PC3
import org.kde.kirigami as Kirigami

MouseArea {
    id: compact

    readonly property var cfg: Plasmoid.configuration
    readonly property bool vertical: Plasmoid.formFactor === PlasmaCore.Types.Vertical
    readonly property bool inPanel: Plasmoid.formFactor === PlasmaCore.Types.Horizontal || vertical
    readonly property var s: root.summary
    readonly property bool showText: inPanel && !vertical && s !== null && cfg.panelShows !== "icon"
    readonly property bool twoLine: cfg.panelStyle === "twoLine" && compact.height >= Kirigami.Units.gridUnit * 1.9

    // the value shown, its colour, and the word that goes with it
    readonly property real budgetPct: s && s.budget_pct !== null ? s.budget_pct : -1
    readonly property string value: !s ? ""
        : cfg.panelShows === "perday" ? root.eur(s.per_day)
        : cfg.panelShows === "spent" ? root.eur(s.spent)
        : cfg.panelShows === "budget" ? (budgetPct < 0 ? "–" : Math.round(budgetPct) + "%")
        : root.eur(s.left)
    readonly property string word: cfg.panelShows === "perday" ? i18n("a day")
        : cfg.panelShows === "spent" ? i18n("spent")
        : cfg.panelShows === "budget" ? i18n("of budget")
        : (s && s.left < 0 ? i18n("over") : i18n("left"))
    readonly property color tone: {
        if (!s || cfg.numberColor === "off") return Kirigami.Theme.textColor;
        if (s.left < 0) return root.bad;
        if (cfg.numberColor === "traffic" && budgetPct >= 0)
            return budgetPct > 100 ? root.bad : budgetPct >= 85 ? root.warn : root.good;
        return Kirigami.Theme.textColor;
    }
    // mini bar: how far through the period, or budget used
    readonly property real barFraction: !s ? 0
        : cfg.panelBar === "period" ? s.period.day / s.period.days_total
        : cfg.panelBar === "budget" ? Math.min(1, Math.max(0, budgetPct) / 100) : 0
    readonly property color barColor: cfg.panelBar === "budget" && budgetPct > 100 ? root.bad
        : cfg.panelBar === "budget" && budgetPct >= 85 ? root.warn : root.good

    Layout.minimumWidth: showText ? row.implicitWidth + Kirigami.Units.smallSpacing * 2 : Kirigami.Units.iconSizes.medium
    Layout.preferredWidth: Layout.minimumWidth
    hoverEnabled: true
    acceptedButtons: Qt.LeftButton | Qt.MiddleButton
    onContainsMouseChanged: if (root.privacy && !root.expanded) root.revealed = containsMouse
    onClicked: function (mouse) {
        if (mouse.button === Qt.MiddleButton) root.refresh();
        else root.expanded = !root.expanded;
    }

    RowLayout {
        id: row
        anchors.centerIn: parent
        height: parent.height
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            visible: compact.cfg.panelIcon !== "none" || !compact.showText
            source: compact.cfg.panelIcon === "mono" ? "wallet-open" : Qt.resolvedUrl("../icons/savings.png")
            Layout.preferredWidth: Math.min(compact.height, Kirigami.Units.iconSizes.medium)
            Layout.preferredHeight: Layout.preferredWidth
            opacity: root.offline ? 0.6 : 1
            Rectangle {   // something waiting for you: an invitation
                visible: root.pendingInvites > 0
                width: Math.max(6, parent.width * 0.32)
                height: width
                radius: width / 2
                anchors.top: parent.top
                anchors.right: parent.right
                color: Kirigami.Theme.highlightColor
                border.color: Kirigami.Theme.backgroundColor
                border.width: 1
            }
        }
        ColumnLayout {
            visible: compact.showText
            spacing: 0
            Layout.alignment: Qt.AlignVCenter
            RowLayout {
                spacing: Kirigami.Units.smallSpacing
                PC3.Label {
                    text: compact.value + (compact.cfg.panelStyle === "labeled" && !compact.twoLine ? " " + compact.word : "")
                    font.bold: true
                    color: compact.tone
                    opacity: root.offline ? 0.6 : 1
                }
                PC3.Label {   // the optional "· €75/day" next to what's left
                    visible: compact.cfg.panelShows === "left" && compact.cfg.showPerDay && !compact.twoLine
                             && compact.s && compact.s.left > 0
                    text: compact.s ? "· " + i18n("%1/day", root.eur(compact.s.per_day)) : ""
                    opacity: root.offline ? 0.45 : 0.7
                }
            }
            PC3.Label {
                visible: compact.twoLine
                text: compact.word + (compact.cfg.panelShows === "left" && compact.cfg.showPerDay && compact.s && compact.s.left > 0
                                      ? " · " + i18n("%1/day", root.eur(compact.s.per_day)) : "")
                font: Kirigami.Theme.smallFont
                opacity: 0.7
            }
            Rectangle {   // mini bar
                visible: compact.cfg.panelBar !== "off"
                Layout.fillWidth: true
                Layout.topMargin: 1
                height: 3
                radius: 1.5
                color: Qt.alpha(Kirigami.Theme.textColor, 0.15)
                Rectangle {
                    width: parent.width * compact.barFraction
                    height: parent.height
                    radius: 1.5
                    color: compact.barColor
                }
            }
        }
        // icon only, but a bar was asked for: under the icon
        Rectangle {
            visible: !compact.showText && compact.cfg.panelBar !== "off" && compact.s !== null
            Layout.preferredWidth: 3
            Layout.preferredHeight: Math.min(compact.height, Kirigami.Units.iconSizes.medium)
            radius: 1.5
            color: Qt.alpha(Kirigami.Theme.textColor, 0.15)
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: parent.height * compact.barFraction
                radius: 1.5
                color: compact.barColor
            }
        }
    }
}
