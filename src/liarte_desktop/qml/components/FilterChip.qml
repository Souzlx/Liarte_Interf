import QtQuick
import QtQuick.Controls

Button {
    id: chip
    property string caption: ""
    property string description: ""
    signal removed
    implicitHeight: 28
    implicitWidth: Math.min(260, label.implicitWidth + 39)
    hoverEnabled: true
    text: caption
    Accessible.name: "Remover filtro: " + caption
    ToolTip.visible: hovered && description.length > 0
    ToolTip.text: description
    ToolTip.delay: 450
    onClicked: removed()
    background: Rectangle {
        color: chip.hovered ? Theme.selected : Theme.subtle
        radius: 6
        border.width: chip.activeFocus ? 2 : 0
        border.color: Theme.accent
    }
    contentItem: Item {
        Text {
            id: label
            textFormat: Text.PlainText
            x: 9
            width: parent.width - 29
            height: parent.height
            verticalAlignment: Text.AlignVCenter
            text: chip.caption
            font.pixelSize: 11
            color: Theme.text
            elide: Text.ElideRight
        }
        Icon {
            anchors.right: parent.right
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            width: 12
            height: 12
            name: "close"
            color: Theme.muted
        }
    }
}
