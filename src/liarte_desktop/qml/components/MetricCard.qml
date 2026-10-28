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
    readonly property var displayMetric: Object.assign({label: "", value: "—", detail: "", full: ""}, metric || {})
    readonly property string completeText: [displayMetric.label + ": " + displayMetric.value, displayMetric.detail, displayMetric.full, issue].filter(Boolean).join("\n")
    readonly property bool informationVisible: (hover.hovered || activeFocus) && visible
    activeFocusOnTab: true
    implicitHeight: 118
    radius: Theme.radius
    color: emphasized ? Theme.hero : Theme.surface
    border.color: activeFocus ? Theme.accent : emphasized ? Theme.hero : Theme.softLine
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
        anchors.fill: parent
        anchors.margins: 17
        spacing: 6
        RowLayout {
            Layout.fillWidth: true
            Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: card.displayMetric.label
                color: card.emphasized ? Theme.heroMuted : Theme.muted
                font.pixelSize: 12
                elide: Text.ElideRight
            }
            Icon {
                objectName: card.objectName + "Issue"
                name: card.issue.length ? "info" : card.iconName
                color: card.emphasized ? Theme.heroMuted : Theme.muted
                Layout.preferredWidth: 17
                Layout.preferredHeight: 17
            }
        }
        Text {
            id: valueText
            objectName: card.objectName + "Value"
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: card.displayMetric.value
            color: card.emphasized ? "#ffffff" : Theme.text
            font.pixelSize: 28
            minimumPixelSize: 17
            fontSizeMode: Text.HorizontalFit
            font.weight: Font.DemiBold
            elide: Text.ElideRight
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
            text: card.displayMetric.detail
            color: card.emphasized ? Theme.heroMuted : Theme.muted
            font.pixelSize: 11
            elide: Text.ElideRight
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
