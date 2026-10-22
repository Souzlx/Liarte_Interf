import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: chart
    property var rows: []
    readonly property real total: rows.reduce((sum, row) => sum + row.value, 0)
    spacing: 13
    Repeater {
        model: chart.rows.slice(0, 6)
        ColumnLayout {
            id: origin
            required property var modelData
            required property int index
            objectName: "originRow" + index
            readonly property real ratio: chart.total > 0 ? modelData.value / chart.total : 0
            property bool ready: false
            Layout.fillWidth: true
            spacing: 6
            Component.onCompleted: Qt.callLater(() => ready = true)
            Accessible.role: Accessible.StaticText
            Accessible.name: modelData.label + ": " + modelData.share
            RowLayout {
                Layout.fillWidth: true
                Text {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: origin.modelData.label
                    font.pixelSize: 12
                    color: Theme.text
                    elide: Text.ElideRight
                }
                Text {
                    textFormat: Text.PlainText
                    text: origin.modelData.share
                    font.pixelSize: 11
                    color: Theme.muted
                }
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 6
                radius: 3
                color: Theme.subtle
                Rectangle {
                    height: parent.height
                    width: parent.width * origin.ratio
                    radius: 3
                    color: Theme.accent
                    transform: Scale {
                        id: growth
                        origin.x: 0
                        origin.y: 0
                        xScale: origin.ready ? 1 : 0
                        Behavior on xScale {
                            enabled: Theme.motionEnabled && chart.visible
                            NumberAnimation {
                                id: growthAnimation
                                duration: 220
                                easing.type: Easing.OutCubic
                            }
                        }
                    }
                }
            }
            HoverHandler {
                id: hover
            }
            ToolTip.visible: hover.hovered
            ToolTip.text: origin.modelData.label + " · US$ " + origin.modelData.value.toLocaleString(Qt.locale("pt_BR"), "f", 3) + " mi · " + origin.modelData.share
            ToolTip.delay: 300
            Connections {
                target: Theme
                function onMotionEnabledChanged() {
                    if (!Theme.motionEnabled)
                        growthAnimation.complete();
                }
            }
        }
    }
    Item {
        Layout.fillHeight: true
    }
    Text {
        textFormat: Text.PlainText
        visible: chart.rows.length === 0
        Layout.fillWidth: true
        Layout.fillHeight: true
        text: "Sem origens para este filtro."
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        color: Theme.muted
        font.pixelSize: 12
    }
}
