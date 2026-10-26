import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "stockComparison"
    property var comparison: ({})
    property var comparisonState: ({})
    property bool controlsEnabled: true
    property bool expanded: false
    property string draftBase: ""
    property string draftTarget: ""
    property string syncedBase: ""
    property string syncedTarget: ""
    property string metricKey: "stock"
    property string dimension: "product"
    readonly property var months: comparisonState.months || []
    readonly property var metrics: comparison.metrics || []
    readonly property var metricOptions: metrics.map(metric => ({value: metric.key, label: metric.label}))
    readonly property var activeMetric: metrics.find(metric => metric.key === metricKey) || metrics[0] || null
    readonly property var rows: activeMetric ? activeMetric[dimension === "branch" ? "branches" : "products"] || [] : []
    readonly property bool draftValid: draftBase !== draftTarget && months.some(month => month.value === draftBase) && months.some(month => month.value === draftTarget)
    readonly property bool canInspect: controlsEnabled && comparisonState.current === true && !comparisonState.busy && activeMetric !== null && activeMetric.available === true
    readonly property var summaryCards: [
        {label: "Base" + (comparison.baseLabel ? " · " + comparison.baseLabel : ""), value: activeMetric ? activeMetric.before || "—" : "—", detail: "Mês de referência"},
        {label: "Comparado" + (comparison.targetLabel ? " · " + comparison.targetLabel : ""), value: activeMetric ? activeMetric.after || "—" : "—", detail: "Mês comparado"},
        {label: "Diferença", value: activeMetric && activeMetric.available ? activeMetric.change || "—" : "—", detail: activeMetric && activeMetric.available ? activeMetric.percentage || "" : "Comparação indisponível"}
    ]
    signal comparisonRequested(string base, string target)
    signal comparisonFocusRequested(string dimension, string key)

    implicitHeight: content.implicitHeight + 32
    radius: Theme.radius
    color: Theme.surface
    border.color: Theme.softLine

    function optionIndex(options, value) {
        return Math.max(0, options.findIndex(option => option.value === value));
    }
    function syncDrafts() {
        const followedState = draftBase === syncedBase && draftTarget === syncedTarget;
        const base = months.some(month => month.value === comparisonState.base) ? comparisonState.base : months.length ? months[0].value : "";
        const target = months.some(month => month.value === comparisonState.target) ? comparisonState.target : months.length ? months[months.length - 1].value : "";
        const validDraft = months.some(month => month.value === draftBase) && months.some(month => month.value === draftTarget);
        if (followedState || !validDraft) {
            draftBase = base;
            draftTarget = target;
        }
        syncedBase = base;
        syncedTarget = target;
    }
    function rowKey(row) {
        return String(row.key || (dimension === "branch" ? row.branch : row.code) || "");
    }
    function rowLabel(row) {
        const key = rowKey(row);
        if (dimension === "branch")
            return row.name || "Filial " + key;
        return key && row.name && key !== row.name ? key + " · " + row.name : row.name || key;
    }
    onComparisonStateChanged: syncDrafts()
    Component.onCompleted: syncDrafts()

    ColumnLayout {
        id: content
        x: 16
        y: 16
        width: parent.width - 32
        spacing: 12

        GridLayout {
            Layout.fillWidth: true
            columns: width >= 520 ? 2 : 1
            columnSpacing: 12
            rowSpacing: 8
            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 5
                Text {
                    Layout.fillWidth: true
                    text: "Comparar dois meses"
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }
                Text {
                    Layout.fillWidth: true
                    text: "Escolha os meses e investigue a contribuição de produtos e filiais."
                    textFormat: Text.PlainText
                    color: Theme.muted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }
            ActionButton {
                objectName: "stockCompareToggle"
                Layout.fillWidth: parent.columns === 1
                Layout.minimumWidth: 0
                text: root.expanded ? "Recolher comparação" : "Comparar meses"
                Accessible.name: root.expanded ? "Recolher o comparador de meses" : "Abrir o comparador de dois meses"
                onClicked: root.expanded = !root.expanded
            }
        }
        ColumnLayout {
            visible: root.expanded
            Layout.fillWidth: true
            spacing: 12
            Text {
                Layout.fillWidth: true
                text: "Os meses pertencem ao período filtrado. Quantidades usam a unidade selecionada na análise mensal."
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
            GridLayout {
                objectName: "stockCompareInputs"
                Layout.fillWidth: true
                columns: width >= 760 ? 4 : width >= 420 ? 2 : 1
                columnSpacing: 10
                rowSpacing: 10
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 5
                    Text {
                        Layout.fillWidth: true
                        text: "Mês base"
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    AppCombo {
                        objectName: "stockCompareBase"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        model: root.months
                        currentIndex: root.optionIndex(model, root.draftBase)
                        enabled: root.controlsEnabled && count > 0
                        Accessible.name: "Mês base da comparação de estoque"
                        onActivated: index => root.draftBase = model[index].value
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 5
                    Text {
                        Layout.fillWidth: true
                        text: "Mês comparado"
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    AppCombo {
                        objectName: "stockCompareTarget"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        model: root.months
                        currentIndex: root.optionIndex(model, root.draftTarget)
                        enabled: root.controlsEnabled && count > 0
                        Accessible.name: "Mês comparado da análise de estoque"
                        onActivated: index => root.draftTarget = model[index].value
                    }
                }
                ActionButton {
                    objectName: "stockCompareSwap"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.alignment: Qt.AlignBottom
                    text: "Inverter meses"
                    enabled: root.controlsEnabled && root.months.length > 1
                    Accessible.name: "Inverter os meses do formulário sem aplicar a comparação"
                    onClicked: {
                        const previous = root.draftBase;
                        root.draftBase = root.draftTarget;
                        root.draftTarget = previous;
                    }
                }
                ActionButton {
                    objectName: "stockCompareApply"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.alignment: Qt.AlignBottom
                    text: root.comparisonState.busy ? "Atualizar escolha" : "Comparar"
                    primary: true
                    enabled: root.controlsEnabled && root.draftValid
                    Accessible.name: "Aplicar os dois meses da comparação"
                    onClicked: root.comparisonRequested(root.draftBase, root.draftTarget)
                }
            }
            Text {
                objectName: "stockCompareDraftNotice"
                Layout.fillWidth: true
                visible: !root.draftValid
                text: root.months.length < 2 ? "São necessários dois meses no período filtrado para comparar." : "Escolha dois meses diferentes."
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }
            ProgressBar {
                Layout.fillWidth: true
                visible: Boolean(root.comparisonState.busy)
                indeterminate: true
            }
            Text {
                objectName: "stockCompareStatus"
                Layout.fillWidth: true
                visible: text.length > 0
                text: root.comparisonState.error || (root.comparisonState.busy ? "Atualizando comparação…" : root.comparison.base && root.comparisonState.current === false ? "Os valores exibidos pertencem à última comparação concluída. Aplique os meses para atualizar." : "")
                textFormat: Text.PlainText
                color: root.comparisonState.error ? Theme.danger : Theme.muted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }
            GridLayout {
                Layout.fillWidth: true
                columns: width >= 560 ? 2 : 1
                columnSpacing: 12
                rowSpacing: 10
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 5
                    Text {
                        Layout.fillWidth: true
                        text: "Indicador"
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    AppCombo {
                        objectName: "stockCompareMetric"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        model: root.metricOptions
                        currentIndex: root.optionIndex(model, root.activeMetric ? root.activeMetric.key : "")
                        enabled: count > 0
                        Accessible.name: "Indicador da comparação entre meses"
                        onActivated: index => root.metricKey = model[index].value
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 5
                    Text {
                        Layout.fillWidth: true
                        text: "Contribuições por"
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    AppCombo {
                        objectName: "stockCompareDimension"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        model: [{value: "product", label: "Produto"}, {value: "branch", label: "Filial"}]
                        currentIndex: root.optionIndex(model, root.dimension)
                        Accessible.name: "Agrupamento das contribuições da comparação"
                        onActivated: index => root.dimension = model[index].value
                    }
                }
            }
            Text {
                objectName: "stockCompareReference"
                Layout.fillWidth: true
                visible: Boolean(root.comparison.baseLabel && root.comparison.targetLabel)
                text: "Resultado: " + (root.comparison.baseLabel || "—") + " → " + (root.comparison.targetLabel || "—") + (root.activeMetric && root.activeMetric.unit ? " · " + root.activeMetric.unit : "")
                textFormat: Text.PlainText
                color: Theme.text
                font.pixelSize: 12
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }
            GridLayout {
                objectName: "stockCompareSummaries"
                Layout.fillWidth: true
                columns: width >= 720 ? 3 : 1
                columnSpacing: 10
                rowSpacing: 10
                Repeater {
                    model: root.summaryCards
                    Rectangle {
                        id: summaryCard
                        required property var modelData
                        required property int index
                        objectName: "stockCompareSummary" + index
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumWidth: 0
                        implicitHeight: summaryContent.implicitHeight + 24
                        radius: 7
                        color: Theme.subtle
                        Accessible.role: Accessible.StaticText
                        Accessible.name: modelData.label + ": " + modelData.value + ". " + modelData.detail
                        ColumnLayout {
                            id: summaryContent
                            x: 12
                            y: 12
                            width: parent.width - 24
                            spacing: 6
                            Text {
                                Layout.fillWidth: true
                                text: summaryCard.modelData.label
                                textFormat: Text.PlainText
                                color: Theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                objectName: summaryCard.objectName + "Value"
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                text: summaryCard.modelData.value
                                textFormat: Text.PlainText
                                color: Theme.text
                                font.pixelSize: 23
                                minimumPixelSize: 16
                                fontSizeMode: Text.HorizontalFit
                                font.weight: Font.DemiBold
                                wrapMode: Text.WrapAnywhere
                            }
                            Text {
                                Layout.fillWidth: true
                                text: summaryCard.modelData.detail
                                textFormat: Text.PlainText
                                visible: text.length > 0
                                color: Theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }
            Text {
                objectName: "stockCompareReason"
                Layout.fillWidth: true
                text: root.activeMetric ? root.activeMetric.reason || "" : "Selecione os meses e aplique a comparação."
                visible: text.length > 0
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: reconciliation.implicitHeight + 24
                visible: root.activeMetric !== null && root.activeMetric.available && (root.activeMetric.key === "stock" || root.activeMetric.key === "quantity")
                radius: 7
                color: Theme.subtle
                ColumnLayout {
                    id: reconciliation
                    x: 12
                    y: 12
                    width: parent.width - 24
                    spacing: 6
                    Text {
                        Layout.fillWidth: true
                        text: "Como a diferença é composta"
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        objectName: "stockCompareReconciliation"
                        Layout.fillWidth: true
                        text: root.activeMetric ? "Posições presentes nos dois meses: " + (root.activeMetric.matched || "—") + "\nRegistros só no mês comparado: " + (root.activeMetric.added || "—") + "\nRegistros só no mês base: " + (root.activeMetric.missing || "—") : ""
                        textFormat: Text.PlainText
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                }
            }
            Text {
                objectName: "stockCompareCoverage"
                Layout.fillWidth: true
                text: root.activeMetric ? root.activeMetric.coverage || "" : ""
                visible: text.length > 0
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
            ColumnLayout {
                objectName: "stockCompareRows"
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: root.rows.slice(0, 12)
                    delegate: Button {
                        id: contributionRow
                        required property var modelData
                        required property int index
                        objectName: "stockCompareRow" + index
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        implicitWidth: 0
                        implicitHeight: rowContent.implicitHeight + 20
                        padding: 10
                        enabled: root.canInspect && root.rowKey(modelData).length > 0
                        Accessible.name: root.rowLabel(modelData) + ". Base: " + (modelData.before || "—") + ". Comparado: " + (modelData.after || "—") + ". Diferença: " + (modelData.change || "—") + ". Investigar histórico."
                        onClicked: root.comparisonFocusRequested(root.dimension, root.rowKey(modelData))
                        background: Rectangle {
                            radius: 7
                            color: contributionRow.hovered ? Theme.hover : contributionRow.index % 2 === 0 ? Theme.subtle : "transparent"
                            border.color: contributionRow.visualFocus ? Theme.accent : "transparent"
                        }
                        contentItem: ColumnLayout {
                            id: rowContent
                            spacing: 5
                            GridLayout {
                                Layout.fillWidth: true
                                columns: width >= 560 ? 2 : 1
                                columnSpacing: 12
                                rowSpacing: 4
                                Text {
                                    objectName: contributionRow.objectName + "Name"
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 0
                                    text: root.rowLabel(contributionRow.modelData)
                                    textFormat: Text.PlainText
                                    color: Theme.text
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.WordWrap
                                }
                                Text {
                                    objectName: contributionRow.objectName + "Change"
                                    Layout.fillWidth: parent.columns === 1
                                    Layout.minimumWidth: 0
                                    Layout.maximumWidth: parent.width >= 560 ? Math.max(150, parent.width * 0.42) : parent.width
                                    text: contributionRow.modelData.change || "—"
                                    textFormat: Text.PlainText
                                    color: Theme.text
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.WrapAnywhere
                                    horizontalAlignment: parent.columns === 1 ? Text.AlignLeft : Text.AlignRight
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: (contributionRow.modelData.before || "—") + " → " + (contributionRow.modelData.after || "—")
                                textFormat: Text.PlainText
                                color: Theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                objectName: contributionRow.objectName + "Detail"
                                Layout.fillWidth: true
                                text: [contributionRow.modelData.detail, contributionRow.modelData.coverage].filter(Boolean).join(" · ")
                                visible: text.length > 0
                                textFormat: Text.PlainText
                                color: Theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
                Text {
                    objectName: "stockCompareEmpty"
                    Layout.fillWidth: true
                    visible: root.activeMetric !== null && root.activeMetric.available && root.rows.length === 0
                    text: "Nenhuma contribuição com diferença neste recorte."
                    textFormat: Text.PlainText
                    color: Theme.muted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }
            Text {
                objectName: "stockCompareNotice"
                Layout.fillWidth: true
                text: root.comparison.notice || ""
                visible: text.length > 0
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                text: "A lista é resumida; o Excel inclui todas as contribuições."
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
        }
    }
}
