import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: section
    objectName: "stockMonthly"
    required property var monthly
    property bool controlsEnabled: true
    property string metricKey: "cost"
    property string rankingKey: "sellers"
    readonly property bool modalOpen: expandedChart.visible
    readonly property var kinds: monthly.seriesKinds || []
    readonly property string effectiveMetric: kinds.some(k => k.value === metricKey) ? metricKey : kinds.length ? kinds[0].value : "cost"
    readonly property var series: (monthly.series || {})[effectiveMetric] || ({})
    readonly property var rankingKinds: [
        {
            value: "sellers",
            label: "Mais vendidos"
        },
        {
            value: "slow",
            label: "Sem venda recente"
        },
        {
            value: "neverSold",
            label: "Sem venda registrada"
        },
        {
            value: "lowTurnover",
            label: "Menor giro da fonte"
        },
        {
            value: "changes",
            label: "Variação do estoque"
        },
        {
            value: "salesChanges",
            label: "Variação de vendas"
        }
    ]
    readonly property var rows: monthly[rankingKey] || []
    readonly property string rankingNote: {
        if (rankingKey === "changes")
            return monthly.comparison || "";
        if (rankingKey === "salesChanges" || rankingKey === "sellers")
            return monthly.salesComparison || "";
        if (rankingKey === "neverSold")
            return "Sem saída positiva registrada até o mês. Não permite concluir ausência de consumo interno ou obsolescência.";
        if (rankingKey === "lowTurnover")
            return "Giro da fonte por posição com saldo positivo; valores não negativos. Não é giro consolidado ou idade dos lotes.";
        return "Tempo desde a última venda observada até o mês selecionado. Não representa a idade física do estoque. Consumo interno não está incluído.";
    }
    signal monthSelected(string period)
    signal unitSelected(string unit)
    signal productSelected(string code)
    spacing: 14

    function optionIndex(options, value) {
        return Math.max(0, options.findIndex(option => option.value === value));
    }
    function syncPlotMonth() {
        const index = (series.points || []).findIndex(point => point.period === monthly.period);
        if (index >= 0)
            monthlyPlot.selectedIndex = index;
    }
    onMonthlyChanged: Qt.callLater(syncPlotMonth)
    onSeriesChanged: Qt.callLater(syncPlotMonth)

    GridLayout {
        Layout.fillWidth: true
        columns: width >= 760 ? 3 : 1
        columnSpacing: 12
        rowSpacing: 12
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: 4
            Text {
                Layout.fillWidth: true
                text: "Análise mensal"
                color: Theme.text
                font.pixelSize: 19
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                text: "Fechamentos, vendas e contribuições dos produtos nas variações."
                color: Theme.muted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }
        }
        ColumnLayout {
            Layout.fillWidth: parent.columns === 1
            Layout.preferredWidth: parent.columns === 1 ? -1 : 180
            Layout.minimumWidth: 0
            spacing: 5
            Text {
                text: "Mês em análise"
                color: Theme.muted
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }
            AppCombo {
                id: monthCombo
                objectName: "stockMonthlyMonth"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                model: section.monthly.months || []
                currentIndex: section.optionIndex(model, section.monthly.period || "")
                enabled: section.controlsEnabled && count > 0
                Accessible.name: "Mês da análise de estoque"
                onActivated: index => section.monthSelected(model[index].value)
            }
        }
        ColumnLayout {
            Layout.fillWidth: parent.columns === 1
            Layout.preferredWidth: parent.columns === 1 ? -1 : 154
            Layout.minimumWidth: 0
            spacing: 5
            Text {
                text: "Unidade das quantidades"
                color: Theme.muted
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }
            AppCombo {
                id: unitCombo
                objectName: "stockMonthlyUnit"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                model: section.monthly.units || []
                currentIndex: section.optionIndex(model, section.monthly.unit || "")
                enabled: section.controlsEnabled && count > 0
                Accessible.name: "Unidade das quantidades na análise mensal"
                onActivated: index => section.unitSelected(model[index].value)
            }
        }
    }
    GridLayout {
        objectName: "stockMonthlyProductFilter"
        visible: Boolean(section.monthly.product)
        Layout.fillWidth: true
        columns: width >= 640 ? 2 : 1
        columnSpacing: 12
        rowSpacing: 8
        Text {
            objectName: "stockMonthlyProductLabel"
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: "Produto: " + (section.monthly.product || "") + (section.monthly.productLabel ? " · " + section.monthly.productLabel : "")
            textFormat: Text.PlainText
            color: Theme.text
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        ActionButton {
            objectName: "stockMonthlyClearProduct"
            Layout.fillWidth: parent.columns === 1
            text: "Todos os produtos"
            subtle: true
            enabled: section.controlsEnabled
            Accessible.name: "Remover o filtro de produto da análise mensal"
            onClicked: section.productSelected("")
        }
    }
    Rectangle {
        Layout.fillWidth: true
        implicitHeight: monthlyContext.implicitHeight + 24
        radius: 8
        color: Theme.subtle
        ColumnLayout {
            id: monthlyContext
            x: 12
            y: 12
            width: parent.width - 24
            spacing: 5
            Text {
                objectName: "stockMonthlyScope"
                Layout.fillWidth: true
                text: (section.monthly.label || "") + (section.monthly.previousLabel ? " · Comparação com " + section.monthly.previousLabel : "")
                textFormat: Text.PlainText
                color: Theme.text
                font.pixelSize: 12
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                text: [section.monthly.scope, section.monthly.salesScope].filter(Boolean).join("\n")
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
            Text {
                objectName: "stockMonthlyNotice"
                visible: text.length > 0
                Layout.fillWidth: true
                text: section.monthly.notice || ""
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
        }
    }
    Text {
        objectName: "stockMonthlyEmpty"
        visible: text.length > 0
        Layout.fillWidth: true
        text: section.monthly.empty || ""
        textFormat: Text.PlainText
        color: Theme.muted
        font.pixelSize: 12
        wrapMode: Text.WordWrap
    }
    GridLayout {
        Layout.fillWidth: true
        columns: width >= 980 ? 4 : width >= 500 ? 2 : 1
        columnSpacing: 12
        rowSpacing: 12
        Repeater {
            model: section.monthly.metrics || []
            Rectangle {
                id: metricCard
                required property var modelData
                required property int index
                objectName: "stockMonthlyMetric" + index
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 0
                implicitHeight: metricContent.implicitHeight + 32
                radius: Theme.radius
                color: Theme.surface
                border.color: Theme.softLine
                Accessible.role: Accessible.StaticText
                Accessible.name: modelData.label + ": " + modelData.value + ". " + (modelData.detail || "")
                Accessible.description: modelData.full || ""
                ToolTip.visible: metricHover.hovered && Boolean(modelData.full)
                ToolTip.text: modelData.full || ""
                ToolTip.delay: 450
                HoverHandler {
                    id: metricHover
                }
                ColumnLayout {
                    id: metricContent
                    x: 16
                    y: 16
                    width: parent.width - 32
                    spacing: 7
                    Text {
                        Layout.fillWidth: true
                        text: metricCard.modelData.label
                        textFormat: Text.PlainText
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        objectName: metricCard.objectName + "Value"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: metricCard.modelData.value
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.pixelSize: 25
                        minimumPixelSize: 17
                        fontSizeMode: Text.HorizontalFit
                        wrapMode: Text.WrapAnywhere
                        font.weight: Font.DemiBold
                    }
                    Text {
                        Layout.fillWidth: true
                        text: metricCard.modelData.detail || ""
                        textFormat: Text.PlainText
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }
    Rectangle {
        objectName: "stockMonthlyChartCard"
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        implicitHeight: chartContent.implicitHeight + 36
        radius: Theme.radius
        color: Theme.surface
        border.color: Theme.softLine
        ColumnLayout {
            id: chartContent
            x: 18
            y: 18
            width: parent.width - 36
            spacing: 10
            GridLayout {
                id: chartHeading
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.preferredWidth: chartContent.width
                columns: width >= 720 ? 3 : 2
                columnSpacing: 10
                rowSpacing: 10
                Text {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.columnSpan: parent.columns === 2 ? 2 : 1
                    text: section.series.title || "Evolução mensal"
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }
                AppCombo {
                    id: metricCombo
                    objectName: "stockMonthlyMetric"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.maximumWidth: 250
                    Layout.preferredWidth: 220
                    model: section.kinds
                    currentIndex: section.optionIndex(model, section.effectiveMetric)
                    Accessible.name: "Indicador do gráfico mensal de estoque"
                    onActivated: index => section.metricKey = model[index].value
                }
                ActionButton {
                    objectName: "stockMonthlyExpand"
                    text: "Ampliar"
                    iconName: "chart"
                    subtle: true
                    implicitWidth: Math.max(108, naturalWidth)
                    Layout.minimumWidth: implicitWidth
                    onClicked: expandedChart.open()
                }
            }
            StockPlot {
                id: monthlyPlot
                objectName: "stockMonthlyPlot"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.preferredHeight: Math.min(330, Math.max(220, width * 0.37))
                points: section.series.points || []
                unit: section.series.unit || "R$"
                seriesName: section.series.title || "Evolução mensal"
                precision: section.effectiveMetric === "cost" ? 2 : 3
                movingAverage: false
                mode: section.effectiveMetric === "sales" ? "column" : "line"
                onPointsChanged: Qt.callLater(section.syncPlotMonth)
            }
            Text {
                objectName: "stockMonthlyChartNote"
                visible: text.length > 0
                Layout.fillWidth: true
                text: section.series.note || ""
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: monthlyReadout.implicitHeight + 20
                color: Theme.subtle
                radius: 7
                Text {
                    id: monthlyReadout
                    objectName: "stockMonthlyReadout"
                    x: 10
                    y: 10
                    width: parent.width - 20
                    text: monthlyPlot.readout || "Use o cursor ou as setas para consultar os meses. O mês da análise é escolhido acima."
                    textFormat: Text.PlainText
                    color: Theme.muted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
    Rectangle {
        objectName: "stockMonthlyRankingCard"
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        implicitHeight: rankingContent.implicitHeight + 36
        radius: Theme.radius
        color: Theme.surface
        border.color: Theme.softLine
        ColumnLayout {
            id: rankingContent
            x: 18
            y: 18
            width: parent.width - 36
            spacing: 12
            GridLayout {
                Layout.fillWidth: true
                columns: width >= 580 ? 2 : 1
                columnSpacing: 12
                rowSpacing: 10
                Text {
                    Layout.fillWidth: true
                    text: "Produtos em análise · " + (section.monthly.label || "")
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }
                AppCombo {
                    objectName: "stockMonthlyTab"
                    Layout.fillWidth: parent.columns === 1
                    Layout.preferredWidth: parent.columns === 1 ? -1 : 230
                    Layout.minimumWidth: 0
                    model: section.rankingKinds
                    currentIndex: section.optionIndex(model, section.rankingKey)
                    Accessible.name: "Lista de produtos da análise mensal"
                    onActivated: index => section.rankingKey = model[index].value
                }
            }
            Text {
                objectName: "stockMonthlyComparison"
                visible: text.length > 0
                Layout.fillWidth: true
                text: section.rankingNote
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
            ColumnLayout {
                objectName: "stockMonthlyRows"
                Layout.fillWidth: true
                spacing: 5
                Repeater {
                    model: section.rows.slice(0, 10)
                    Button {
                        id: productRow
                        required property var modelData
                        required property int index
                        objectName: "stockMonthlyRow" + index
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        implicitWidth: 0
                        implicitHeight: productContent.implicitHeight + topPadding + bottomPadding
                        padding: 10
                        enabled: section.controlsEnabled
                        hoverEnabled: true
                        Accessible.name: modelData.code + " · " + modelData.name + ": " + modelData.display + ". " + (modelData.detail || "") + ". Analisar produto."
                        onClicked: section.productSelected(modelData.code)
                        background: Rectangle {
                            radius: 7
                            color: productRow.hovered ? Theme.hover : productRow.index % 2 === 0 ? Theme.subtle : "transparent"
                            border.color: productRow.visualFocus ? Theme.accent : "transparent"
                        }
                        contentItem: ColumnLayout {
                            id: productContent
                            spacing: 5
                            GridLayout {
                                Layout.fillWidth: true
                                columns: width >= 560 ? 2 : 1
                                columnSpacing: 14
                                rowSpacing: 4
                                Text {
                                    objectName: productRow.objectName + "Name"
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 0
                                    text: (productRow.index + 1) + ". " + productRow.modelData.code + " · " + productRow.modelData.name
                                    textFormat: Text.PlainText
                                    color: Theme.text
                                    font.pixelSize: 12
                                    font.weight: Font.Medium
                                    wrapMode: Text.WordWrap
                                }
                                Text {
                                    objectName: productRow.objectName + "Value"
                                    Layout.fillWidth: parent.columns === 1
                                    Layout.minimumWidth: 0
                                    Layout.maximumWidth: parent.width >= 560 ? Math.max(160, parent.width * 0.42) : parent.width
                                    text: productRow.modelData.display + (productRow.modelData.share ? " · " + productRow.modelData.share : "")
                                    textFormat: Text.PlainText
                                    color: Theme.text
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.WrapAnywhere
                                    horizontalAlignment: parent.columns === 1 ? Text.AlignLeft : Text.AlignRight
                                }
                            }
                            Text {
                                objectName: productRow.objectName + "Detail"
                                visible: text.length > 0
                                Layout.fillWidth: true
                                text: productRow.modelData.detail || ""
                                textFormat: Text.PlainText
                                color: Theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
                Text {
                    visible: !section.rows.length
                    Layout.fillWidth: true
                    text: "Sem produtos com dados válidos nesta análise."
                    color: Theme.muted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }
            Text {
                visible: section.rows.length > 0
                Layout.fillWidth: true
                text: (section.rows.length > 10 ? "10 primeiros produtos · " : "") + "Selecione um produto para acompanhar sua evolução."
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
        }
    }
    ChartDialog {
        id: expandedChart
        objectName: "stockMonthlyChartDialog"
        stock: true
        title: section.series.title || "Evolução mensal"
        contextLabel: (section.monthly.scope || "") + (section.series.note ? "\n" + section.series.note : "")
        legendLabel: section.series.title || "Mensal"
        points: section.series.points || []
        unit: monthlyPlot.unit
        precision: monthlyPlot.precision
        mode: monthlyPlot.mode
        movingAverage: false
    }
}
