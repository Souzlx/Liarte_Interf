import QtQuick
import QtQuick.Controls

CheckBox {
    id: box
    property bool wrapLabel: false
    implicitHeight: wrapLabel ? Math.max(28, contentItem.implicitHeight + topPadding + bottomPadding) : 28
    font.pixelSize: 12
    spacing: 8
    indicator: Rectangle {
        x: 2
        y: (box.height - height) / 2
        width: 17
        height: 17
        radius: 3
        color: box.checked ? Theme.primary : Theme.surface
        border.color: box.activeFocus ? Theme.accent : Theme.muted
        border.width: box.activeFocus ? 2 : 1
        Icon {
            anchors.centerIn: parent
            width: 13
            height: 13
            name: "check"
            color: "white"
            visible: box.checked
        }
    }
    contentItem: Text {
        textFormat: Text.PlainText
        text: box.text
        font: box.font
        color: box.enabled ? Theme.text : Theme.muted
        leftPadding: 26
        verticalAlignment: Text.AlignVCenter
        wrapMode: box.wrapLabel ? Text.WordWrap : Text.NoWrap
        elide: box.wrapLabel ? Text.ElideNone : Text.ElideRight
    }
}
