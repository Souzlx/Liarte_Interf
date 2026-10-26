pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "stockOverviewSection"
    required property var view
    property bool current: true
    property bool controlsEnabled: true
    readonly property string chartKey: chartMeasure.currentValue || "history"
    readonly property string chartMode: stockTrend.mode
    readonly property bool chartMovingAverage: stockTrend.movingAverage
    readonly property bool chartShowValues: stockTrend.showValues
    readonly property bool chartHasAverage: stockTrend.hasAverage
    property alias plot: stockTrend
    signal chartRequested
    signal productSelected(string code)
    signal activitySelected(string activity)
    spacing: 16

    GridLayout {
        objectName: "stockPrimaryMetrics"
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        columns: width >= 760 ? 3 : width >= 500 ? 2 : 1
        columnSpacing: 12
        rowSpacing: 12
        Repeater {
            model: (root.view.metrics || []).length > 3 ? [0, 1, 3] : []
            MetricCard {
                required property int modelData
                objectName: "stockMetric" + modelData
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                metric: (root.view.metrics || [])[modelData] || ({label: "", value: "—", detail: "", full: ""})
                emphasized: modelData === 0
                iconName: modelData === 0 ? "price" : "box"
            }
        }
    }
    GridLayout {
        Layout.fillWidth: true
        columns: width >= 650 ? 2 : 1
        columnSpacing: 12
        rowSpacing: 10
        Text {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: "Entenda o estoque"
            textFormat: Text.PlainText
            color: Theme.text
            font.pixelSize: 17
            font.weight: Font.DemiBold
            wrapMode: Text.WordWrap
        }
        AppCombo {
            id: chartMeasure
            objectName: "stockOverviewMeasure"
            Layout.fillWidth: parent.columns === 1
            Layout.minimumWidth: 0
            Layout.preferredWidth: 250
            model: [
                {
                    value: "history",
                    label: "Evolução do estoque"
                },
                {
                    value: "capital",
                    label: "Capital por produto"
                }
            ]
            Accessible.name: "Análise do panorama de estoque"
        }
    }
    Rectangle {
        id: stockHistoryCard
        visible: root.chartKey === "history"
        objectName: "stockHistoryCard"
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumWidth: 0
        Layout.preferredHeight: stockHistoryContent.implicitHeight + 36
        color: Theme.surface
        radius: Theme.radius
        border.color: Theme.softLine
        ColumnLayout {
            id: stockHistoryContent
            anchors.fill: parent
            anchors.margins: 18
            spacing: 7
            GridLayout {
                id: stockChartHeading
                Layout.fillWidth: true
                columns: width >= stockChartTitle.implicitWidth + stockChartMode.implicitWidth + openStockChart.implicitWidth + 24 ? 3 : 2
                rowSpacing: 8
                Text {
                    id: stockChartTitle
                    Layout.fillWidth: true
                    Layout.columnSpan: stockChartHeading.columns === 2 ? 2 : 1
                    text: "Evolução do estoque"
                    color: Theme.text
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }
                AppCombo {
                    id: stockChartMode
                    objectName: "stockChartMode"
                    Layout.preferredWidth: 112
                    model: [
                        {
                            value: "line",
                            label: "Linhas"
                        },
                        {
                            value: "column",
                            label: "Colunas"
                        }
                    ]
                    Accessible.name: "Tipo de gráfico de estoque"
                }
                ActionButton {
                    id: openStockChart
                    objectName: "openStockChart"
                    text: "Ampliar"
                    iconName: "chart"
                    implicitWidth: Math.max(112, naturalWidth)
                    Layout.minimumWidth: implicitWidth
                    font.pixelSize: 11
                    subtle: true
                    onClicked: root.chartRequested()
                }
            }
            GridLayout {
                Layout.fillWidth: true
                columns: width >= 460 ? 2 : 1
                rowSpacing: 4
                Text {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: root.view.historySummary.value || "—"
                    color: Theme.text
                    font.pixelSize: 24
                    minimumPixelSize: 18
                    fontSizeMode: Text.HorizontalFit
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                    ToolTip.visible: summaryHover.hovered
                    ToolTip.text: root.view.historySummary.full || ""
                    HoverHandler {
                        id: summaryHover
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: root.view.historySummary.change || ""
                    color: Theme.muted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
            }
            Text {
                Layout.fillWidth: true
                text: (root.view.historySummary.period || "") + " · " + root.view.historicalScope
                textFormat: Text.PlainText
                font.pixelSize: 11
                color: Theme.muted
                wrapMode: Text.WordWrap
            }
            StockPlot {
                id: stockTrend
                objectName: "stockTrend"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 220
                Layout.preferredHeight: Math.min(330, Math.max(220, stockHistoryCard.width * 0.45))
                points: root.view.plotTrend || []
                mode: stockChartMode.currentValue || "line"
                showValues: stockValues.checked
                movingAverage: stockAverage.checked
            }
            GridLayout {
                id: stockChartLegend
                Layout.fillWidth: true
                columns: width >= 360 ? 3 : 2
                columnSpacing: 8
                rowSpacing: 4
                RowLayout {
                    Layout.columnSpan: stockChartLegend.columns === 2 ? 2 : 1
                    Rectangle {
                        Layout.preferredWidth: 16
                        Layout.preferredHeight: 3
                        radius: 1
                        color: Theme.accent
                    }
                    Text {
                        text: "Custo"
                        color: Theme.muted
                        font.pixelSize: 11
                    }
                }
                StockToggle {
                    id: stockAverage
                    objectName: "stockAverage"
                    text: "Média 3m"
                    checked: true
                    font.pixelSize: 11
                    Accessible.name: "Exibir média móvel de três meses"
                }
                StockToggle {
                    id: stockValues
                    objectName: "stockValues"
                    text: "Valores"
                    font.pixelSize: 11
                }
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: stockTrendReadout.implicitHeight + 20
                radius: 7
                color: Theme.subtle
                Text {
                    id: stockTrendReadout
                    objectName: "stockTrendReadout"
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 10
                    text: stockTrend.readout || "Passe o cursor ou use as setas. Meses sem fechamento permanecem em branco."
                    textFormat: Text.PlainText
                    color: Theme.muted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
    Rectangle {
        objectName: "stockCapitalCard"
        visible: root.chartKey === "capital"
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumWidth: 0
        Layout.preferredHeight: stockCapitalContent.implicitHeight + 36
        radius: Theme.radius
        color: Theme.surface
        border.color: Theme.softLine
        ColumnLayout {
            id: stockCapitalContent
            anchors.fill: parent
            anchors.margins: 18
            spacing: 7
            Text {
                Layout.fillWidth: true
                text: "Capital por produto"
                color: Theme.text
                font.pixelSize: 15
                font.weight: Font.DemiBold
            }
            Text {
                Layout.fillWidth: true
                text: Math.min(8, root.view.ranking.length) + " maiores · custo e participação no capital positivo"
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
            StockBars {
                id: stockRanking
                objectName: "stockRanking"
                Layout.fillWidth: true
                rows: root.view.ranking.slice(0, 8)
                interactive: root.controlsEnabled && root.current
                onSelected: code => root.productSelected(code)
            }
            Item {
                Layout.fillHeight: true
            }
            Text {
                Layout.fillWidth: true
                text: stockRanking.rows.length ? "Acumulado: " + stockRanking.rows[stockRanking.rows.length - 1].cumulative + " · selecione um produto para analisar" : "Sem capital positivo no recorte"
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }
        }
    }
    StockToggle {
        id: activityToggle
        objectName: "stockActivityToggle"
        Layout.fillWidth: true
        text: "Ver capital por última venda"
        Accessible.name: "Exibir a distribuição do capital por última venda observada"
    }
    Rectangle {
        visible: activityToggle.checked
        Layout.fillWidth: true
        implicitHeight: activityColumn.implicitHeight + 36
        radius: Theme.radius
        color: Theme.surface
        border.color: Theme.softLine
        ColumnLayout {
            id: activityColumn
            x: 18
            y: 18
            width: parent.width - 36
            spacing: 12
            Text {
                text: "Capital positivo por última venda"
                color: Theme.text
                font.pixelSize: 15
                font.weight: Font.DemiBold
            }
            GridLayout {
                Layout.fillWidth: true
                columns: root.width < 700 ? 2 : 4
                columnSpacing: 12
                rowSpacing: 12
                Repeater {
                    model: root.view.activityChart
                    Button {
                        id: activityButton
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: 64
                        enabled: root.controlsEnabled && root.current
                        padding: 10
                        onClicked: root.activitySelected(modelData.name)
                        Accessible.name: modelData.name + ": " + modelData.display + ". Filtrar."
                        background: Rectangle {
                            color: activityButton.hovered ? Theme.selected : Theme.subtle
                            radius: 7
                            border.color: activityButton.visualFocus ? Theme.accent : "transparent"
                        }
                        contentItem: ColumnLayout {
                            Text {
                                text: activityButton.modelData.name
                                color: Theme.muted
                                font.pixelSize: 11
                            }
                            Text {
                                Layout.fillWidth: true
                                text: activityButton.modelData.display
                                color: Theme.text
                                font.pixelSize: 16
                                font.weight: Font.DemiBold
                                fontSizeMode: Text.HorizontalFit
                                minimumPixelSize: 12
                            }
                        }
                    }
                }
            }
        }
    }
}
