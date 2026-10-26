pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: chart
    property var rows: []
    property bool interactive: false
    signal originSelected(string country)
    readonly property real total: rows.reduce((sum, row) => sum + row.value, 0)
    spacing: width < 300 ? 12 : 14
    function displayValue(value) {
        if (value >= 1000)
            return "US$ " + (value / 1000).toLocaleString(Qt.locale("pt_BR"), "f", 2) + " bi";
        if (value >= 1)
            return "US$ " + value.toLocaleString(Qt.locale("pt_BR"), "f", 2) + " mi";
        if (value >= 0.01)
            return "US$ " + value.toLocaleString(Qt.locale("pt_BR"), "f", 3) + " mi";
        return "US$ " + (value * 1000000).toLocaleString(Qt.locale("pt_BR"), "f", 2);
    }
    Repeater {
        model: chart.rows.slice(0, 6)
        Button {
            id: origin
            required property var modelData
            required property int index
            objectName: "originRow" + index
            readonly property real ratio: chart.total > 0 ? modelData.value / chart.total : 0
            readonly property string amount: chart.displayValue(modelData.value)
            readonly property string exactAmount: modelData.full || "US$ " + (modelData.value * 1000000).toLocaleString(Qt.locale("pt_BR"), "f", 2)
            property bool ready: false
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            implicitWidth: 0
            implicitHeight: originContent.implicitHeight + topPadding + bottomPadding
            padding: 3
            hoverEnabled: true
            focusPolicy: chart.interactive ? Qt.StrongFocus : Qt.NoFocus
            Component.onCompleted: Qt.callLater(() => ready = true)
            Accessible.role: chart.interactive ? Accessible.Button : Accessible.StaticText
            Accessible.name: modelData.label + ": " + modelData.share + ", " + exactAmount + (chart.interactive ? ". Filtrar esta origem." : "")
            Accessible.description: chart.interactive ? "Pressione Enter ou espaço para analisar somente esta origem." : ""
            onClicked: if (chart.interactive)
                chart.originSelected(modelData.label)
            Keys.onReturnPressed: if (chart.interactive)
                chart.originSelected(modelData.label)
            Keys.onEnterPressed: if (chart.interactive)
                chart.originSelected(modelData.label)
            background: Rectangle {
                radius: 5
                color: origin.hovered && chart.interactive ? Theme.hover : "transparent"
                border.color: origin.visualFocus ? Theme.accent : "transparent"
            }
            contentItem: ColumnLayout {
                id: originContent
                spacing: 6
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        objectName: "originLabel" + origin.index
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: origin.modelData.label
                        font.pixelSize: 12
                        color: Theme.text
                        elide: Text.ElideRight
                    }
                    Text {
                        objectName: "originShare" + origin.index
                        textFormat: Text.PlainText
                        text: origin.modelData.share
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        color: Theme.text
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 20
                        implicitHeight: 7
                        radius: 4
                        color: Theme.subtle
                        Rectangle {
                            height: parent.height
                            width: parent.width * origin.ratio
                            radius: 4
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
                    Text {
                        objectName: "originAmount" + origin.index
                        textFormat: Text.PlainText
                        text: origin.amount
                        font.pixelSize: 10
                        color: Theme.muted
                        horizontalAlignment: Text.AlignRight
                    }
                }
            }
            ToolTip.visible: hovered || activeFocus
            ToolTip.text: origin.modelData.label + " · " + origin.exactAmount + " · " + origin.modelData.share + (chart.interactive ? "\nFiltrar esta origem" : "")
            ToolTip.delay: activeFocus ? 0 : 300
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
