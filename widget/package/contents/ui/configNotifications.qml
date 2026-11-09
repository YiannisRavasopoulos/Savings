// Settings → Notifications: which events become desktop notifications.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    property alias cfg_notifyInvites: invites.checked
    property alias cfg_notifyShared: shared.checked
    property alias cfg_notifyReset: reset.checked
    property alias cfg_notifyRecurring: recurring.checked
    property alias cfg_notifyBudgets: budgets.checked

    Kirigami.FormLayout {
        QQC2.CheckBox {
            id: invites
            Kirigami.FormData.label: i18n("Notify me about:")
            text: i18n("Invitations to shared categories")
        }
        QQC2.CheckBox {
            id: shared
            text: i18n("Changes in my shared categories (someone joins, leaves, changes shares…)")
        }
        QQC2.CheckBox {
            id: reset
            text: i18n("My budget period resetting soon (3 days before)")
        }
        QQC2.CheckBox {
            id: recurring
            text: i18n("Recurring payments being added")
        }
        QQC2.CheckBox {
            id: budgets
            text: i18n("A category reaching 90 % or going over its budget")
        }
        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 24
            wrapMode: Text.WordWrap
            font: Kirigami.Theme.smallFont
            opacity: 0.8
            text: i18n("Shown as normal Plasma notifications, each one once. The widget checks whenever it refreshes, so something that happened while this PC was off appears the next time it's on. Clicking a notification opens that page of Savings in your browser. Accepting or declining an invitation happens in Savings.")
        }
    }
}
