import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: chart
    property var rows: []
    property bool interactive: false
    signal selected(string code)
    readonly property real maximum: Math.max(1, ...rows.map(r => r.value))
    spacing: 3
    Repeater {
        model: chart.rows
        Button {
            id: bar
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: 37
            hoverEnabled: true
            focusPolicy: chart.interactive ? Qt.StrongFocus : Qt.NoFocus
            Accessible.name: modelData.name + ": " + modelData.display
            onClicked: if (chart.interactive)
                chart.selected(modelData.code)
            padding: 3
            background: Rectangle {
                radius: 5
                color: bar.hovered && chart.interactive ? Theme.hover : "transparent"
                border.color: bar.visualFocus ? Theme.accent : "transparent"
            }
            contentItem: ColumnLayout {
                spacing: 6
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        text: bar.modelData.name
                        color: Theme.text
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                    Text {
                        textFormat: Text.PlainText
                        text: bar.modelData.display
                        color: Theme.text
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                    }
                    Text {
                        textFormat: Text.PlainText
                        text: bar.modelData.share || ""
                        Layout.preferredWidth: 42
                        horizontalAlignment: Text.AlignRight
                        color: Theme.muted
                        font.pixelSize: 10
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    height: 9
                    radius: 2
                    color: Theme.subtle
                    Rectangle {
                        width: parent.width * Math.max(0, Math.min(1, bar.modelData.value / chart.maximum))
                        height: parent.height
                        radius: 2
                        color: Theme.accent
                    }
                }
            }
            ToolTip.visible: hovered
            ToolTip.text: modelData.name + " · " + modelData.display + (modelData.cumulative ? "\nAcumulado: " + modelData.cumulative : "") + (chart.interactive ? "\nSelecionar produto" : "")
            ToolTip.delay: 400
        }
    }
    Text {
        Layout.fillWidth: true
        visible: !chart.rows.length
        text: "Sem valores neste recorte."
        color: Theme.muted
        font.pixelSize: 12
        textFormat: Text.PlainText
    }
}
