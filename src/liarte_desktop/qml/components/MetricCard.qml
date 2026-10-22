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
    implicitHeight: 118
    radius: Theme.radius
    color: emphasized ? Theme.hero : Theme.surface
    border.color: emphasized ? Theme.hero : Theme.softLine
    Accessible.role: Accessible.StaticText
    Accessible.name: metric.label + ": " + metric.value + ". " + metric.detail
    readonly property string issue: metric.issue || ""
    Accessible.description: [metric.full, issue].filter(Boolean).join(" ")
    HoverHandler {
        id: hover
    }
    ToolTip.visible: hover.hovered
    ToolTip.text: [metric.full, issue].filter(Boolean).join("\n")
    ToolTip.delay: 450
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
                text: card.metric.label
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
            text: card.metric.value
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
            text: card.metric.detail
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
