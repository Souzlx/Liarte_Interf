pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: trendPanel
    required property var buying
    required property string shownKind
    readonly property string trendKey: trendMetric.currentValue || "value"
    readonly property var trendData: buying.series[trendKey] || buying.series.value || ({
            points: [],
            unit: "US$ mi",
            precision: 2,
            change: "—",
            comparison: "",
            hasRolling: false,
            rollingLabel: ""
        })
    readonly property var lastTrendPoint: trendData.points.length ? trendData.points[trendData.points.length - 1] : ({
            label: "",
            display: "—"
        })
    readonly property bool modalOpen: trendMetric.popup.visible
    readonly property bool zoomed: monthlyChart.zoomed
    readonly property bool allowNegative: monthlyChart.allowNegative
    readonly property string metricContext: {
        if (["price", "fob", "freight"].includes(trendKey))
            return buying.isMix ? "Média unitária do mix · a composição pode explicar variações. Selecione um produto para comparar origens." : "Referência histórica em US$/kg · não é cotação de fornecedor.";
        if (trendKey === "weight")
            return "Peso líquido publicado · kg, sem conversão entre produtos.";
        const basis = shownKind === "municipal" ? "FOB" : "CIF inclui frete e seguro";
        if (trendKey === "valueChange")
            return "Variação percentual em relação ao mês anterior · valor nominal em US$ · " + basis + ".";
        return "Valores nominais em US$ · " + basis + ".";
    }
    signal expandRequested
    signal valuesRequested
    signal revealRequested(var control)
    function focusFirst() {
        trendMetric.forceActiveFocus(Qt.TabFocusReason);
    }
    objectName: "trendPanel"
    Layout.fillWidth: true
    Layout.fillHeight: true
    Layout.preferredWidth: 660
    Layout.minimumWidth: 0
    Layout.preferredHeight: trendContent.implicitHeight + 36
    color: Theme.surface
    radius: Theme.radius
    border.color: Theme.softLine
    ColumnLayout {
        id: trendContent
        anchors.fill: parent
        anchors.margins: 18
        spacing: 8
        GridLayout {
            id: trendHeading
            Layout.fillWidth: true
            columns: width >= trendTitle.implicitWidth + trendMetric.implicitWidth + openTrendChart.implicitWidth + 2 * columnSpacing ? 3 : 2
            rowSpacing: 8
            Text {
                id: trendTitle
                Layout.fillWidth: true
                Layout.columnSpan: trendHeading.columns === 2 ? 2 : 1
                textFormat: Text.PlainText
                text: "Evolução mensal"
                color: Theme.text
                font.pixelSize: 14
                font.weight: Font.DemiBold
            }
            AppCombo {
                id: trendMetric
                objectName: "trendMetric"
                property string selectedMetricKey: "value"
                Layout.fillWidth: true
                Layout.preferredWidth: 160
                implicitHeight: 34
                font.pixelSize: 12
                Accessible.name: "Indicador do gráfico mensal"
                onActivated: selectedMetricKey = currentValue
                onModelChanged: Qt.callLater(() => {
                    const matchingIndex = model.findIndex(item => item.value === selectedMetricKey);
                    currentIndex = matchingIndex >= 0 ? matchingIndex : 0;
                })
                model: trendPanel.shownKind === "municipal" ? [
                    {
                        label: "Valor FOB",
                        value: "value"
                    },
                    {
                        label: trendPanel.buying.isMix ? "Média FOB/kg · mix" : "FOB/kg",
                        value: "price"
                    },
                    {
                        label: "Peso",
                        value: "weight"
                    },
                    {
                        label: "Variação (%)",
                        value: "valueChange"
                    }
                ] : [
                    {
                        label: "Valor CIF",
                        value: "value"
                    },
                    {
                        label: trendPanel.buying.isMix ? "Média CIF/kg · mix" : "CIF/kg",
                        value: "price"
                    },
                    {
                        label: trendPanel.buying.isMix ? "Média FOB/kg · mix" : "FOB/kg",
                        value: "fob"
                    },
                    {
                        label: trendPanel.buying.isMix ? "Média frete/kg · mix" : "Frete/kg",
                        value: "freight"
                    },
                    {
                        label: "Peso",
                        value: "weight"
                    },
                    {
                        label: "Variação (%)",
                        value: "valueChange"
                    }
                ]
                onActiveFocusChanged: if (activeFocus)
                    trendPanel.revealRequested(trendMetric)
            }
            ActionButton {
                id: openTrendChart
                objectName: "openTrendChart"
                text: "Ampliar"
                iconName: "chart"
                implicitHeight: 30
                implicitWidth: Math.max(112, naturalWidth)
                Layout.minimumWidth: implicitWidth
                font.pixelSize: 11
                subtle: true
                onClicked: trendPanel.expandRequested()
            }
        }
        GridLayout {
            Layout.fillWidth: true
            columns: width >= 500 ? 2 : 1
            columnSpacing: 18
            rowSpacing: 4
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: trendPanel.lastTrendPoint.display || "—"
                color: Theme.text
                font.pixelSize: 27
                minimumPixelSize: 18
                fontSizeMode: Text.HorizontalFit
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }
            ColumnLayout {
                spacing: 2
                Text {
                    text: trendPanel.trendData.change
                    color: Theme.text
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
                Text {
                    Layout.fillWidth: true
                    text: trendPanel.trendData.comparison
                    color: Theme.muted
                    font.pixelSize: 11
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                }
            }
        }
        Text {
            Layout.fillWidth: true
            text: [trendPanel.lastTrendPoint.label, trendPanel.trendData.coverage || ""].filter(Boolean).join(" · ")
            color: Theme.muted
            font.pixelSize: 11
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        Text {
            objectName: "importTrendContext"
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: trendPanel.metricContext
            color: Theme.muted
            font.pixelSize: 11
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        GridLayout {
            id: trendActions
            Layout.fillWidth: true
            Layout.maximumWidth: Infinity
            columns: parent.width >= priceScale.implicitWidth + openTrendValues.implicitWidth + 2 * columnSpacing ? 3 : 1
            AppCheck {
                id: priceScale
                objectName: "priceScale"
                Layout.minimumWidth: 0
                Layout.maximumWidth: trendActions.parent.width
                wrapLabel: true
                text: "Ampliar variação"
                visible: ["price", "fob", "freight"].includes(trendPanel.trendKey)
                font.pixelSize: 11
                ToolTip.visible: hovered
                ToolTip.text: "Ajusta o eixo para comparar pequenas diferenças. Os valores permanecem iguais."
            }
            Item {
                visible: trendActions.columns === 3
                Layout.fillWidth: true
            }
            ActionButton {
                id: openTrendValues
                objectName: "openTrendValues"
                text: "Ver valores"
                iconName: "grid"
                implicitHeight: 30
                implicitWidth: Math.max(132, naturalWidth)
                Layout.minimumWidth: implicitWidth
                font.pixelSize: 11
                subtle: true
                onClicked: trendPanel.valuesRequested()
            }
        }
        LinePlot {
            id: monthlyChart
            objectName: "monthlyChart"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 220
            Layout.preferredHeight: Math.min(310, Math.max(220, trendPanel.width * 0.42))
            points: trendPanel.trendData.points
            unit: trendPanel.trendData.unit
            precision: trendPanel.trendData.precision
            allowNegative: trendPanel.trendKey === "valueChange"
            zoomed: priceScale.checked && ["price", "fob", "freight"].includes(trendPanel.trendKey)
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 7
            Rectangle {
                Layout.preferredWidth: 16
                Layout.preferredHeight: 2
                color: Theme.accent
            }
            Text {
                text: "Mensal"
                color: Theme.muted
                font.pixelSize: 10
            }
            Item {
                Layout.preferredWidth: 8
                Layout.preferredHeight: 1
            }
            Item {
                visible: trendPanel.trendData.hasRolling
                Layout.preferredWidth: 16
                Layout.preferredHeight: 2
                Row {
                    spacing: 2
                    Repeater {
                        model: 3
                        Rectangle {
                            width: 4
                            height: 2
                            color: Theme.muted
                        }
                    }
                }
            }
            Text {
                visible: trendPanel.trendData.hasRolling
                text: trendPanel.trendData.rollingLabel
                color: Theme.muted
                font.pixelSize: 10
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
        }
        Text {
            visible: Boolean(trendPanel.trendData.periodChange) && trendPanel.trendData.periodChange !== "—"
            Layout.fillWidth: true
            text: "Primeiro → último mês: " + (trendPanel.trendData.periodChange || "—")
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: trendReadout.implicitHeight + 20
            radius: 7
            color: Theme.subtle
            Text {
                id: trendReadout
                objectName: "trendReadout"
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 10
                text: monthlyChart.readout.replace(/\n/g, " · ") || "Passe o cursor ou use as setas para consultar os meses."
                textFormat: Text.PlainText
                color: Theme.text
                font.pixelSize: 11
                wrapMode: Text.WordWrap
                Accessible.name: monthlyChart.readout
            }
        }
        Text {
            objectName: "axisScaleNotice"
            visible: monthlyChart.croppedAxis
            Layout.fillWidth: true
            text: "Eixo ajustado · a escala não começa em zero"
            color: Theme.muted
            font.pixelSize: 10
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
    }
}
