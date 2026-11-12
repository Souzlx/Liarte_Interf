import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: card
    property var metric: ({
            label: "",
            value: "—",
            detail: "",
            full: ""
        })
    property bool emphasized: false
    property string iconName: "chart"
    property color iconColor: Theme.iconColor
    property color iconBackground: Theme.iconTint
    readonly property var displayMetric: Object.assign({label: "", value: "—", detail: "", full: ""}, metric || {})
    readonly property string completeText: [displayMetric.label + ": " + displayMetric.value, displayMetric.detail, displayMetric.full, issue].filter(Boolean).join("\n")
    readonly property bool informationVisible: (hover.hovered || activeFocus) && visible
    activeFocusOnTab: true
    implicitHeight: Math.max(128, content.implicitHeight + 36)
    Layout.minimumHeight: implicitHeight
    Layout.minimumWidth: 0
    radius: Theme.radius
    color: emphasized ? Theme.hero : Theme.surface
    border.color: activeFocus ? Theme.focus : emphasized ? Theme.hero : Theme.line
    border.width: activeFocus ? 2 : 1
    Accessible.role: Accessible.StaticText
    Accessible.name: displayMetric.label + ": " + displayMetric.value + ". " + displayMetric.detail
    readonly property string issue: displayMetric.issue || ""
    HoverHandler {
        id: hover
    }
    Accessible.description: completeText
    ToolTip.visible: informationVisible
    ToolTip.text: completeText
    ToolTip.delay: activeFocus ? 0 : 450
    onVisibleChanged: {
        if (!visible) {
            fade.stop();
            valueText.opacity = 1;
        }
    }
    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.margins: 18
        height: implicitHeight
        spacing: 8
        RowLayout {
            Layout.fillWidth: true
            Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: card.displayMetric.label
                color: card.emphasized ? Theme.heroMuted : Theme.muted
                font.pixelSize: 12
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
            }
            Rectangle {
                Layout.preferredWidth: 30
                Layout.preferredHeight: 30
                radius: Theme.controlRadius
                color: card.emphasized ? Qt.rgba(1, 1, 1, 0.12) : card.iconBackground
                Icon {
                    objectName: card.objectName + "Issue"
                    anchors.centerIn: parent
                    name: card.issue.length ? "info" : card.iconName
                    color: card.emphasized ? Theme.heroMuted : card.iconColor
                    width: 17
                    height: 17
                }
            }
        }
        Text {
            id: valueText
            objectName: card.objectName + "Value"
            textFormat: Text.PlainText
            Layout.fillWidth: true
            Layout.minimumHeight: 32
            text: card.displayMetric.value
            color: card.emphasized ? "#ffffff" : Theme.text
            font.pixelSize: 26
            minimumPixelSize: 17
            fontSizeMode: Text.HorizontalFit
            font.weight: Font.DemiBold
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
            onTextChanged: {
                if (!Theme.motionEnabled || !card.visible)
                    opacity = 1;
                else
                    fade.restart();
            }
            OpacityAnimator {
                id: fade
                target: valueText
                from: 0.55
                to: 1
                duration: Theme.motion
                easing.type: Easing.OutCubic
            }
        }
        Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            Layout.minimumHeight: 16
            text: card.displayMetric.detail
            color: card.emphasized ? Theme.heroMuted : Theme.muted
            font.pixelSize: 11
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
    }
    Connections {
        target: Theme
        function onMotionEnabledChanged() {
            if (!Theme.motionEnabled) {
                fade.stop();
                valueText.opacity = 1;
            }
        }
    }
}
