import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Button {
    id: button
    property bool primary: false
    property bool subtle: false
    property string iconName: ""
    readonly property real naturalWidth: Math.ceil(implicitContentWidth + leftPadding + rightPadding)
    readonly property color fillColor: {
        if (!enabled)
            return Theme.subtle;
        if (primary) {
            if (down)
                return "#0f2c48";
            return hovered ? Theme.primaryHover : Theme.primary;
        }
        if (down)
            return Theme.selected;
        if (hovered)
            return Theme.subtle;
        return subtle ? "transparent" : Theme.surface;
    }
    implicitHeight: 42
    implicitWidth: Math.max(100, naturalWidth)
    hoverEnabled: true
    font.pixelSize: 13
    font.weight: primary ? Font.DemiBold : Font.Medium
    leftPadding: 14
    rightPadding: 14
    contentItem: Item {
        implicitWidth: contentRow.implicitWidth
        implicitHeight: Math.max(20, contentRow.implicitHeight)
        RowLayout {
            id: contentRow
            anchors.centerIn: parent
            width: Math.min(parent.width, implicitWidth)
            spacing: 7
            Icon {
                visible: button.iconName.length > 0
                name: button.iconName
                color: !button.enabled ? Theme.muted : button.primary ? "white" : Theme.text
                Layout.preferredWidth: 17
                Layout.preferredHeight: 17
            }
            Text {
                visible: button.text.length > 0
                Layout.fillWidth: true
                textFormat: Text.PlainText
                text: button.text
                font: button.font
                color: !button.enabled ? Theme.muted : button.primary ? "white" : Theme.text
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
        }
    }
    background: Rectangle {
        radius: 7
        color: button.fillColor
        border.color: button.visualFocus ? Theme.accent : button.primary ? Theme.primary : Theme.line

        border.width: button.visualFocus ? 2 : button.subtle ? 0 : 1
        Behavior on color {
            enabled: Theme.motionEnabled && button.visible
            ColorAnimation {
                duration: Theme.fast
            }
        }
    }
}
