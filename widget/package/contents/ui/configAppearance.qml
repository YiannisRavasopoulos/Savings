// Settings → Appearance: how the panel and the popup look.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    id: page

    property string cfg_panelShows
    property string cfg_panelStyle
    property string cfg_panelBar
    property string cfg_numberColor
    property string cfg_panelIcon
    property alias cfg_privacy: privacy.checked
    property string cfg_primaryTab
    property string cfg_sections
    property string cfg_hiddenSections
    property string cfg_whereChart
    property int cfg_trendPeriods
    property alias cfg_showFuture: showFuture.checked
    property string cfg_density
    property string cfg_popupSize
    property string cfg_numberFormat
    property alias cfg_wholeEuros: whole.checked

    readonly property var sectionNames: ({
        left: i18n("Left over"), stats: i18n("Income · Spent · Budget used"), where: i18n("Where it went"),
        trend: i18n("Spent vs income"), budgets: i18n("Budgets"), recent: i18n("Recent")
    })
    readonly property var allSections: ["left", "stats", "where", "trend", "budgets", "recent"]

    // a ComboBox bound to a string setting: [[value, label], ...]
    component Choice: QQC2.ComboBox {
        id: box
        property var options: []
        property string value
        signal picked(string v)
        model: options.map(function (o) { return o[1]; })
        currentIndex: Math.max(0, options.findIndex(function (o) { return String(o[0]) === String(box.value); }))
        onActivated: function (i) { box.picked(String(options[i][0])); }
    }

    function order() {
        var saved = (cfg_sections || "").split(",").filter(function (n) { return allSections.indexOf(n) >= 0; });
        return saved.concat(allSections.filter(function (n) { return saved.indexOf(n) < 0; }));
    }
    function hidden() { return (cfg_hiddenSections || "").split(",").filter(function (n) { return n !== ""; }); }

    Kirigami.FormLayout {
        Item { Kirigami.FormData.isSection: true; Kirigami.FormData.label: i18n("Panel") }

        Choice {
            Kirigami.FormData.label: i18n("Shows:")
            options: [["left", i18n("What's left")], ["perday", i18n("Left per day")], ["spent", i18n("Spent this period")],
                      ["budget", i18n("Budget used (%)")], ["icon", i18n("Icon only")]]
            value: page.cfg_panelShows
            onPicked: function (v) { page.cfg_panelShows = v; }
        }
        Choice {
            Kirigami.FormData.label: i18n("Text:")
            enabled: page.cfg_panelShows !== "icon"
            options: [["plain", i18n("Plain (€1,820)")], ["labeled", i18n("With a word (€1,820 left)")],
                      ["twoLine", i18n("Two lines (for tall panels)")]]
            value: page.cfg_panelStyle
            onPicked: function (v) { page.cfg_panelStyle = v; }
        }
        Choice {
            Kirigami.FormData.label: i18n("Mini bar:")
            options: [["off", i18n("None")], ["period", i18n("How far through the period")], ["budget", i18n("Budget used")]]
            value: page.cfg_panelBar
            onPicked: function (v) { page.cfg_panelBar = v; }
        }
        Choice {
            Kirigami.FormData.label: i18n("Colour the number:")
            enabled: page.cfg_panelShows !== "icon"
            options: [["off", i18n("No")], ["over", i18n("Red only when over")], ["traffic", i18n("Green / amber / red by budget use")]]
            value: page.cfg_numberColor
            onPicked: function (v) { page.cfg_numberColor = v; }
        }
        Choice {
            Kirigami.FormData.label: i18n("Icon:")
            options: [["logo", i18n("Savings logo")], ["mono", i18n("Monochrome (follows the panel)")], ["none", i18n("None")]]
            value: page.cfg_panelIcon
            onPicked: function (v) { page.cfg_panelIcon = v; }
        }
        QQC2.CheckBox {
            id: privacy
            Kirigami.FormData.label: i18n("Privacy:")
            text: i18n("Hide amounts (€•••) until I hover the panel or click in the popup")
        }

        Item { Kirigami.FormData.isSection: true; Kirigami.FormData.label: i18n("Popup") }

        Choice {
            Kirigami.FormData.label: i18n("Open on:")
            options: [["overview", i18n("Overview")], ["budget", i18n("Budget (savings vs budget)")]]
            value: page.cfg_primaryTab
            onPicked: function (v) { page.cfg_primaryTab = v; }
        }

        ColumnLayout {
            Kirigami.FormData.label: i18n("Overview sections:")
            spacing: 0
            Repeater {
                model: page.order()
                RowLayout {
                    required property string modelData
                    required property int index
                    QQC2.CheckBox {
                        text: page.sectionNames[modelData]
                        checked: page.hidden().indexOf(modelData) < 0
                        Layout.fillWidth: true
                        onToggled: {
                            var h = page.hidden().filter(function (n) { return n !== modelData; });
                            if (!checked) h.push(modelData);
                            page.cfg_hiddenSections = h.join(",");
                        }
                    }
                    QQC2.ToolButton {
                        icon.name: "arrow-up"
                        enabled: index > 0
                        onClicked: { var o = page.order(); var t = o[index]; o[index] = o[index - 1]; o[index - 1] = t; page.cfg_sections = o.join(","); }
                        QQC2.ToolTip.text: i18n("Move up")
                        QQC2.ToolTip.visible: hovered
                    }
                    QQC2.ToolButton {
                        icon.name: "arrow-down"
                        enabled: index < page.allSections.length - 1
                        onClicked: { var o = page.order(); var t = o[index]; o[index] = o[index + 1]; o[index + 1] = t; page.cfg_sections = o.join(","); }
                        QQC2.ToolTip.text: i18n("Move down")
                        QQC2.ToolTip.visible: hovered
                    }
                }
            }
            QQC2.Button {
                text: i18n("Reset to default")
                icon.name: "edit-undo"
                onClicked: { page.cfg_sections = page.allSections.join(","); page.cfg_hiddenSections = ""; }
            }
        }
        Choice {
            Kirigami.FormData.label: i18n("Where it went:")
            options: [["doughnut", i18n("Doughnut")], ["bars", i18n("Horizontal bars")]]
            value: page.cfg_whereChart
            onPicked: function (v) { page.cfg_whereChart = v; }
        }
        Choice {
            Kirigami.FormData.label: i18n("Spent vs income:")
            options: [[3, i18n("Last 3 periods")], [6, i18n("Last 6 periods")], [12, i18n("Last 12 periods")]]
            value: String(page.cfg_trendPeriods)
            onPicked: function (v) { page.cfg_trendPeriods = parseInt(v); }
        }
        QQC2.CheckBox {
            id: showFuture
            Kirigami.FormData.label: i18n("Charts:")
            text: i18n("Show future-dated spending (lighter)")
        }
        Choice {
            Kirigami.FormData.label: i18n("Density:")
            options: [["comfortable", i18n("Comfortable")], ["compact", i18n("Compact")]]
            value: page.cfg_density
            onPicked: function (v) { page.cfg_density = v; }
        }
        Choice {
            Kirigami.FormData.label: i18n("Size:")
            options: [["small", i18n("Small")], ["medium", i18n("Medium")], ["large", i18n("Large")]]
            value: page.cfg_popupSize
            onPicked: function (v) { page.cfg_popupSize = v; }
        }

        Item { Kirigami.FormData.isSection: true; Kirigami.FormData.label: i18n("Numbers") }

        Choice {
            Kirigami.FormData.label: i18n("Format:")
            options: [["en", "€1,820.30"], ["eu", "€1.820,30"]]
            value: page.cfg_numberFormat
            onPicked: function (v) { page.cfg_numberFormat = v; }
        }
        QQC2.CheckBox {
            id: whole
            text: i18n("Whole euros only (€1,820)")
        }
    }
}
