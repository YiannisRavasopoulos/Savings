import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    property alias cfg_serverUrl: server.text
    property alias cfg_token: token.text
    property alias cfg_refreshMinutes: refresh.value
    property alias cfg_showPerDay: perDay.checked
    // set by Plasma for every config entry; not edited here
    property string cfg_cache
    property string cfg_cacheDefault
    property string cfg_serverUrlDefault
    property string cfg_tokenDefault
    property int cfg_refreshMinutesDefault
    property bool cfg_showPerDayDefault

    Kirigami.FormLayout {
        QQC2.TextField {
            id: server
            Kirigami.FormData.label: i18n("Server address:")
            placeholderText: "http://192.168.0.10:8090"
            Layout.minimumWidth: Kirigami.Units.gridUnit * 18
        }
        QQC2.TextField {
            id: token
            Kirigami.FormData.label: i18n("Widget token:")
            echoMode: showToken.checked ? TextInput.Normal : TextInput.Password
            placeholderText: "svw_…"
            Layout.minimumWidth: Kirigami.Units.gridUnit * 18
        }
        QQC2.CheckBox {
            id: showToken
            text: i18n("Show token")
        }
        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 22
            wrapMode: Text.WordWrap
            font: Kirigami.Theme.smallFont
            opacity: 0.8
            text: i18n("Create a token in Savings → Settings → KDE widget, then paste it here. The server address is the one you open Savings with in the browser.")
        }
        Item { Kirigami.FormData.isSection: true }
        QQC2.SpinBox {
            id: refresh
            Kirigami.FormData.label: i18n("Refresh every (minutes):")
            from: 1
            to: 120
        }
        QQC2.CheckBox {
            id: perDay
            Kirigami.FormData.label: i18n("Panel:")
            text: i18n("Show the per-day amount next to what's left")
        }
    }
}
