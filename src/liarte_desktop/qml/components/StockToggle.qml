import QtQuick
import QtQuick.Controls

CheckBox {
    id: control
    implicitHeight: 30
    spacing: 6
    padding: 4
    hoverEnabled: true
    indicator: Rectangle {
        implicitWidth: 15
        implicitHeight: 15
        x: control.leftPadding
        y: (control.height - height) / 2
        radius: 3
        color: control.checked ? Theme.accent : Theme.surface
        border.color: control.activeFocus ? Theme.accent : Theme.line
        Text {
            anchors.centerIn: parent
            text: control.checked ? "✓" : ""
            color: "white"
            font.pixelSize: 11
            font.weight: Font.Bold
        }
    }
    contentItem: Text {
        text: control.text
        leftPadding: control.indicator.width + control.spacing
        color: Theme.muted
        font.pixelSize: 11
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        color: control.hovered ? Theme.hover : "transparent"
        radius: 4
        border.color: control.visualFocus ? Theme.accent : "transparent"
    }
}
