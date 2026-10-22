import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    default property alias bodyContent: bodyColumn.data
    property bool closeButton: true
    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    width: Math.min(510, parent ? parent.width - 32 : 510)
    padding: 18
    topPadding: 2
    bottomPadding: 12
    readonly property real bodyLimit: Math.max(70, (parent ? parent.height : 640) - header.implicitHeight - footer.implicitHeight - 52)
    background: Rectangle {
        color: Theme.surface
        border.color: Theme.line
        radius: 12
    }
    header: Text {
        text: dialog.title
        textFormat: Text.PlainText
        font.pixelSize: 16
        font.weight: Font.DemiBold
        color: Theme.text
        leftPadding: 18
        rightPadding: 18
        topPadding: 18
        bottomPadding: 15
        elide: Text.ElideRight
    }
    contentItem: ScrollView {
        id: scroll
        clip: true
        implicitHeight: Math.min(bodyColumn.implicitHeight, dialog.bodyLimit)
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            id: bodyColumn
            width: scroll.availableWidth
            spacing: 12
        }
    }
    footer: Item {
        implicitHeight: dialog.closeButton ? 57 : 0
        visible: dialog.closeButton
        ActionButton {
            anchors {
                right: parent.right
                top: parent.top
                margins: 12
            }
            text: "Fechar"
            Accessible.name: "Fechar diálogo"
            onClicked: dialog.close()
        }
    }
    enter: Transition {
        NumberAnimation {
            property: "opacity"
            from: 0
            to: 1
            duration: Theme.motion
        }
    }
    exit: Transition {
        NumberAnimation {
            property: "opacity"
            from: 1
            to: 0
            duration: Theme.motion
        }
    }
    Overlay.modal: Rectangle {
        color: Theme.dark ? "#9a000000" : "#550d2639"
    }
}
