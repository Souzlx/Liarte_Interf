import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AppDialog {
    id: dialog
    property bool stock: false
    property var points: []
    property string unit: "US$ mi"
    property int precision: 2
    property string contextLabel: ""
    property string legendLabel: "Mensal"
    property string mode: "line"
    property bool movingAverage: true
    property bool showValues: false
    property bool zoomed: false
    property bool allowNegative: false
    width: Math.min(1120, parent ? parent.width - 32 : 1120)
    onOpened: Qt.callLater(() => {
        if (expandedChart.item)
            expandedChart.item.forceActiveFocus();
    })
    Text {
        id: context
        Layout.fillWidth: true
        text: dialog.contextLabel
        textFormat: Text.PlainText
        font.pixelSize: 12
        color: Theme.muted
        wrapMode: Text.WordWrap
    }
    Loader {
        id: expandedChart
        Layout.fillWidth: true
        Layout.preferredHeight: Math.max(150, Math.min(470, dialog.bodyLimit - context.implicitHeight - readout.implicitHeight - 28))
        active: dialog.visible
        sourceComponent: dialog.stock ? stockPlot : importPlot
    }
    Text {
        Layout.fillWidth: true
        text: dialog.legendLabel
        font.pixelSize: 11
        color: Theme.muted
        wrapMode: Text.WordWrap
    }
    Text {
        id: readout
        Layout.fillWidth: true
        text: expandedChart.item && expandedChart.item.readout ? expandedChart.item.readout.replace(/\n/g, " · ") : "Passe o cursor ou use as setas para consultar os valores."
        textFormat: Text.PlainText
        font.pixelSize: 12
        color: Theme.text
        wrapMode: Text.WordWrap
    }
    Text {
        visible: !dialog.stock && expandedChart.item !== null && Boolean(expandedChart.item.croppedAxis)
        Layout.fillWidth: true
        text: "Eixo ajustado · a escala não começa em zero"
        font.pixelSize: 11
        color: Theme.muted
        wrapMode: Text.WordWrap
    }
    Component {
        id: importPlot
        LinePlot {
            objectName: dialog.objectName + "Plot"
            points: dialog.points
            unit: dialog.unit
            precision: dialog.precision
            zoomed: dialog.zoomed
            allowNegative: dialog.allowNegative
        }
    }
    Component {
        id: stockPlot
        StockPlot {
            objectName: dialog.objectName + "Plot"
            points: dialog.points
            unit: dialog.unit
            precision: dialog.precision
            mode: dialog.mode
            movingAverage: dialog.movingAverage
            showValues: dialog.showValues
            seriesName: dialog.title
        }
    }
}
