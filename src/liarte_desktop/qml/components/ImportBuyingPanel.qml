pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: buyingSection
    required property var workspace
    required property var backend
    readonly property string minimumWeight: originMinWeight.currentValue || "0"
    readonly property string order: originOrder.currentValue || "volume"
    readonly property bool modalOpen: originMinWeight.popup.visible || originOrder.popup.visible
    function focusFirst() {
        const control = buyingSection.workspace.buying.comparable ? originMinWeight : chooseProductAction;
        control.forceActiveFocus(Qt.TabFocusReason);
        buyingSection.workspace.reveal(control);
    }
    objectName: "buyingSection"
    visible: buyingSection.workspace.viewState.loaded
    Layout.fillWidth: true
    spacing: 12
    RowLayout {
        Layout.fillWidth: true
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: "Referências de compra"
            color: Theme.text
            font.pixelSize: 15
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
        }
        Item {
            Layout.fillWidth: true
        }
        Text {
            text: buyingSection.workspace.buying.productLabel
            color: Theme.muted
            font.pixelSize: 11
            textFormat: Text.PlainText
            Layout.maximumWidth: 175
            Layout.preferredWidth: 140
            wrapMode: Text.WordWrap
        }
    }
    GridLayout {
        Layout.fillWidth: true
        columns: buyingSection.width > 930 ? 4 : buyingSection.width > 440 ? 2 : 1
        columnSpacing: 12
        rowSpacing: 12
        Repeater {
            model: buyingSection.workspace.buying.cards
            MetricCard {
                required property var modelData
                required property int index
                objectName: "buyingMetric" + index
                Layout.fillWidth: true
                Layout.preferredHeight: 108
                metric: modelData
                iconName: ["price", "chart", "weight", "grid"][index]
            }
        }
    }
    Rectangle {
        id: comparisonPanel
        objectName: "comparisonPanel"
        Layout.fillWidth: true
        implicitHeight: comparisonContent.implicitHeight + 36
        radius: Theme.radius
        color: Theme.surface
        border.color: Theme.softLine
        ColumnLayout {
            id: comparisonContent
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 18
            spacing: 12
            GridLayout {
                Layout.fillWidth: true
                columns: comparisonPanel.width > 650 ? 4 : 2
                columnSpacing: 10
                rowSpacing: 8
                Text {
                    text: "Preço por origem"
                    color: Theme.text
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
                Item {
                    Layout.fillWidth: true
                }
                AppCombo {
                    id: originMinWeight
                    objectName: "originMinWeight"
                    visible: buyingSection.workspace.buying.comparable
                    Layout.preferredWidth: 140
                    implicitHeight: 34
                    font.pixelSize: 12
                    currentIndex: 1
                    model: [
                        {
                            label: "Sem mínimo",
                            value: "0"
                        },
                        {
                            label: "≥ 1.000 kg",
                            value: "1000"
                        },
                        {
                            label: "≥ 10.000 kg",
                            value: "10000"
                        },
                        {
                            label: "≥ 50.000 kg",
                            value: "50000"
                        }
                    ]
                    onCurrentValueChanged: buyingSection.workspace.originLimit = 8
                    Accessible.name: "Peso mínimo por país no comparador"
                    ToolTip.visible: hovered
                    ToolTip.text: "Peso acumulado por país no período. Altera apenas este comparador; os totais e documentos mantêm seus filtros."
                    ToolTip.delay: 600
                    onActiveFocusChanged: if (activeFocus)
                        buyingSection.workspace.reveal(originMinWeight)
                }
                AppCombo {
                    id: originOrder
                    objectName: "originOrder"
                    visible: buyingSection.workspace.buying.comparable
                    Layout.preferredWidth: 165
                    implicitHeight: 34
                    font.pixelSize: 12
                    model: [
                        {
                            label: "Maior volume",
                            value: "volume"
                        },
                        {
                            label: "Menor valor/kg",
                            value: "low"
                        },
                        {
                            label: "Maior valor/kg",
                            value: "high"
                        }
                    ]
                    Accessible.name: "Ordenar comparação de países"
                    onCurrentValueChanged: buyingSection.workspace.originLimit = 8
                }
                ActionButton {
                    id: chooseProductAction
                    objectName: "chooseComparisonProduct"
                    visible: !buyingSection.workspace.buying.comparable && !buyingSection.workspace.buying.empty
                    text: "Selecionar produto"
                    primary: false
                    Layout.preferredWidth: 165
                    implicitHeight: 34
                    onClicked: buyingSection.workspace.chooseProduct()
                }
            }
            Text {
                visible: !buyingSection.workspace.buying.comparable
                Layout.fillWidth: true
                text: buyingSection.workspace.buying.empty ? "Nenhuma importação para estes filtros." : "Escolha um produto para comparar as origens."
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 12
            }
            ActionButton {
                objectName: "recoverEmptyFilters"
                visible: buyingSection.workspace.buying.empty && buyingSection.workspace.viewState.filterCount > 0
                text: "Limpar filtros"
                implicitHeight: 34
                onClicked: buyingSection.backend.clearFilters()
            }
            OriginComparison {
                id: priceComparison
                objectName: "priceComparison"
                visible: buyingSection.workspace.buying.comparable
                Layout.fillWidth: true
                rows: buyingSection.workspace.matchingOrigins.slice(0, buyingSection.workspace.originLimit)
                basis: buyingSection.workspace.valueBasis
                reference: buyingSection.workspace.buying.reference === undefined ? null : buyingSection.workspace.buying.reference
                onOriginChosen: name => buyingSection.backend.setFilters("country", [name])
            }
            Text {
                visible: buyingSection.workspace.buying.comparable && priceComparison.rows.length === 0
                Layout.fillWidth: true
                text: "Nenhuma origem atinge o peso mínimo selecionado."
                wrapMode: Text.WordWrap
                color: Theme.muted
                font.pixelSize: 12
                textFormat: Text.PlainText
            }
            Text {
                visible: buyingSection.workspace.buying.comparable
                Layout.fillWidth: true
                text: priceComparison.rows.length + " de " + buyingSection.workspace.matchingOrigins.length + " origens · Média do recorte: " + buyingSection.workspace.buying.referenceText + "/kg" + (priceComparison.graphic ? " (traço vertical)" : "")
                wrapMode: Text.WordWrap
                color: Theme.muted
                font.pixelSize: 11
                textFormat: Text.PlainText
            }
            ActionButton {
                objectName: "moreOrigins"
                visible: buyingSection.workspace.matchingOrigins.length > buyingSection.workspace.originLimit
                text: "Mostrar mais origens"
                implicitHeight: 32
                font.pixelSize: 11
                onClicked: buyingSection.workspace.originLimit += 8
            }
            Text {
                visible: buyingSection.workspace.buying.comparable
                Layout.fillWidth: true
                text: buyingSection.workspace.buying.range
                wrapMode: Text.WordWrap
                color: Theme.muted
                font.pixelSize: 11
                textFormat: Text.PlainText
            }
            ActionButton {
                objectName: "toggleMethodology"
                text: buyingSection.workspace.methodologyExpanded ? "Ocultar explicação" : "Como interpretar"
                iconName: "info"
                subtle: true
                implicitHeight: 30
                font.pixelSize: 11
                onClicked: buyingSection.workspace.methodologyExpanded = !buyingSection.workspace.methodologyExpanded
            }
            Text {
                visible: buyingSection.workspace.methodologyExpanded
                Layout.fillWidth: true
                text: buyingSection.workspace.buying.note
                wrapMode: Text.WordWrap
                color: Theme.muted
                font.pixelSize: 11
                textFormat: Text.PlainText
            }
        }
    }
}
