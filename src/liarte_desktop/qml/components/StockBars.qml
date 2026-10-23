import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: chart
    property var rows: []
    property bool interactive: false
    signal selected(string code)
    readonly property real maximum: Math.max(1, ...rows.map(r => r.value))
    readonly property bool compact: width < 380
    readonly property real valueColumnWidth: Math.max(86, amountMetrics.advanceWidth + 6)
    spacing: 6
    TextMetrics {
        id: amountMetrics
        font.pixelSize: 11
        font.weight: Font.DemiBold
        text: chart.rows.reduce((longest, row) => (row.display || "").length > longest.length ? row.display : longest, "")
    }
    Repeater {
        model: chart.rows
        Button {
            id: bar
            required property var modelData
            required property int index
            readonly property real ratio: Math.max(0, Math.min(1, modelData.value / chart.maximum))
            objectName: chart.objectName + "Row" + index
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            implicitWidth: 0
            implicitHeight: Math.max(chart.compact ? 68 : 49, barContent.implicitHeight + topPadding + bottomPadding)
            hoverEnabled: true
            focusPolicy: chart.interactive ? Qt.StrongFocus : Qt.NoFocus
            Accessible.name: (index + 1) + ". " + modelData.name + ": " + modelData.display + (modelData.share ? ", " + modelData.share : "")
            onClicked: if (chart.interactive)
                chart.selected(modelData.code)
            padding: 5
            background: Rectangle {
                radius: 7
                color: bar.hovered && chart.interactive ? Theme.hover : "transparent"
                border.color: bar.visualFocus ? Theme.accent : "transparent"
            }
            contentItem: ColumnLayout {
                id: barContent
                spacing: 7
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Rectangle {
                        Layout.preferredWidth: 21
                        Layout.preferredHeight: 21
                        radius: 5
                        color: Theme.subtle
                        Text {
                            anchors.centerIn: parent
                            text: bar.index + 1
                            font.pixelSize: 10
                            font.weight: Font.Medium
                            color: Theme.muted
                        }
                    }
                    Text {
                        objectName: bar.objectName + "Name"
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: bar.modelData.name
                        color: Theme.text
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                    Text {
                        visible: !chart.compact
                        objectName: bar.objectName + "Amount"
                        textFormat: Text.PlainText
                        Layout.preferredWidth: Math.max(chart.valueColumnWidth, implicitWidth + 2)
                        Layout.minimumWidth: implicitWidth + 2
                        horizontalAlignment: Text.AlignRight
                        text: bar.modelData.display
                        color: Theme.text
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                    }
                    Text {
                        visible: !chart.compact && !!bar.modelData.share
                        textFormat: Text.PlainText
                        text: bar.modelData.share || ""
                        Layout.preferredWidth: Math.max(45, implicitWidth + 2)
                        Layout.minimumWidth: implicitWidth + 2
                        horizontalAlignment: Text.AlignRight
                        color: Theme.muted
                        font.pixelSize: 11
                    }
                }
                GridLayout {
                    id: compactNumbers
                    visible: chart.compact
                    Layout.fillWidth: true
                    Layout.leftMargin: 29
                    columns: width >= compactAmountMetrics.advanceWidth + compactShare.implicitWidth + columnSpacing + 2 ? 2 : 1
                    columnSpacing: 8
                    rowSpacing: 3
                    TextMetrics {
                        id: compactAmountMetrics
                        font: compactAmount.font
                        text: bar.modelData.display
                    }
                    Text {
                        id: compactAmount
                        objectName: bar.objectName + "CompactAmount"
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: bar.modelData.display
                        color: Theme.text
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        wrapMode: Text.WrapAnywhere
                    }
                    Text {
                        id: compactShare
                        objectName: bar.objectName + "CompactShare"
                        textFormat: Text.PlainText
                        Layout.fillWidth: compactNumbers.columns === 1
                        horizontalAlignment: Text.AlignRight
                        text: bar.modelData.share || ""
                        color: Theme.muted
                        font.pixelSize: 11
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 7
                    radius: 3.5
                    color: Theme.subtle
                    Rectangle {
                        width: parent.width * bar.ratio
                        height: parent.height
                        radius: 3.5
                        color: Theme.accent
                    }
                }
            }
            ToolTip.visible: hovered
            ToolTip.text: modelData.name + " · " + modelData.display + (modelData.share ? " · " + modelData.share : "") + (modelData.cumulative ? "\nAcumulado: " + modelData.cumulative : "") + (chart.interactive ? "\nSelecionar produto" : "")
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
