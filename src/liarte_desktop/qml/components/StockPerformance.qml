pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AppDialog {
    id: dialog
    objectName: "stockPerformanceDialog"
    required property var performance
    property bool controlsEnabled: true
    readonly property var viewState: performance.state || ({})
    readonly property var summary: performance.summary || ({})
    readonly property var detail: performance.detail || ({})
    readonly property bool investigating: Boolean(detail.code)
    readonly property bool canInspect: controlsEnabled && viewState.current === true && !viewState.busy
    readonly property var units: viewState.units || []
    readonly property var windows: viewState.windows || []
    readonly property var sorts: [
        {
            value: "most",
            label: "Mais vendidos"
        },
        {
            value: "least",
            label: "Menor venda com saldo"
        },
        {
            value: "decline",
            label: "Maior queda nas vendas"
        },
        {
            value: "turnover",
            label: "Giro mensal da fonte (mediana)"
        },
        {
            value: "stockCost",
            label: "Estoque a custo no fechamento"
        },
        {
            value: "stockQuantity",
            label: "Saldo no fechamento"
        },
        {
            value: "coverage",
            label: "Cobertura estimada"
        },
        {
            value: "all",
            label: "Todos os produtos"
        }
    ]
    property string draftUnit: ""
    property string draftWindow: "3"
    property string draftSort: "most"
    property string draftQuery: ""
    property string syncedChoice: ""
    property string measure: "sales"
    property string inspectedCode: ""
    property string inspectedUnit: ""
    property bool contextExpanded: false
    readonly property string criticalReason: typeof summary.reason === "string" ? summary.reason : String(summary.notice || "")
    readonly property string contextNotice: typeof summary.reason === "string" ? String(summary.notice || "") : ""
    readonly property string draftSortField: sortField(draftSort)
    readonly property bool directionAvailable: draftSort === "turnover" || draftSort.startsWith("metric:")
    readonly property bool draftDescending: draftSort.endsWith(":desc") || draftSort === "most"
    readonly property string directionLabel: draftSort === "all" ? "Código crescente" : draftSortField === "name" ? (draftDescending ? "Z–A" : "A–Z") : (draftDescending ? "Maior primeiro" : "Menor primeiro")
    readonly property var seriesKinds: detail.seriesKinds || []
    readonly property string effectiveMeasure: seriesKinds.some(item => item.value === measure) ? measure : seriesKinds.length ? seriesKinds[0].value : "sales"
    readonly property var series: (detail.series || {})[effectiveMeasure] || ({})
    readonly property bool validChoice: units.some(item => String(item.value) === draftUnit) && windows.some(item => String(item.value) === draftWindow)
    readonly property bool unapplied: choice(draftUnit, draftWindow, draftSort, draftQuery) !== choice(viewState.unit, viewState.window, viewState.sort, viewState.query)
    signal productFocusRequested(string code, string unit)

    title: investigating ? "Investigar produto" : "Desempenho dos produtos"
    width: Math.min(980, parent ? parent.width - 32 : 980)
    height: Math.min(800, parent ? parent.height - 32 : 800)

    function choice(unit, window, sort, query) {
        return JSON.stringify([String(unit || ""), String(window || "3"), String(sort || "most"), String(query || "")]);
    }
    function optionIndex(options, value) {
        return Math.max(0, options.findIndex(item => String(item.value) === String(value)));
    }
    function sortField(order) {
        if (order.startsWith("metric:"))
            return order.split(":")[1];
        return order === "all" ? "name" : order === "turnover" ? "turnover" : "";
    }
    function sortOption(order) {
        const field = sortField(order);
        return field === "name" ? "all" : field || order;
    }
    function chooseSort(option) {
        if (["turnover", "stockCost", "stockQuantity", "coverage"].includes(option))
            draftSort = "metric:" + option + ":desc";
        else if (option === "all")
            draftSort = "metric:name:asc";
        else
            draftSort = option;
    }
    function reverseDirection() {
        if (directionAvailable)
            draftSort = "metric:" + draftSortField + ":" + (draftDescending ? "asc" : "desc");
    }
    function syncDrafts() {
        const applied = choice(viewState.unit, viewState.window, viewState.sort, viewState.query);
        const followed = !syncedChoice || choice(draftUnit, draftWindow, draftSort, draftQuery) === syncedChoice;
        if (followed) {
            draftUnit = String(viewState.unit || "");
            draftWindow = String(viewState.window || "3");
            draftSort = String(viewState.sort || "most");
            draftQuery = String(viewState.query || "");
        }
        if (!units.some(item => String(item.value) === draftUnit))
            draftUnit = units.length ? String(units[0].value) : "";
        if (!windows.some(item => String(item.value) === draftWindow))
            draftWindow = windows.length ? String(windows[0].value) : "3";
        syncedChoice = applied;
    }
    function applyChoice() {
        if (controlsEnabled && !viewState.busy && validChoice)
            performance.configure(draftUnit, Number(draftWindow), draftSort, draftQuery);
    }
    function resetScroll() {
        if (bodyViewport)
            bodyViewport.contentY = 0;
    }
    function returnToList() {
        performance.closeDetail();
        Qt.callLater(() => {
            const index = (summary.rows || []).findIndex(row => row.code === inspectedCode && row.unit === inspectedUnit);
            const item = index >= 0 ? productRows.itemAt(index) : null;
            if (item && item.enabled) {
                item.forceActiveFocus(Qt.BacktabFocusReason);
                dialog.reveal(item);
            } else if (search.enabled)
                search.forceActiveFocus(Qt.BacktabFocusReason);
        });
    }
    function refreshIfNeeded() {
        if (visible && viewState.available && !viewState.current && !viewState.busy && !viewState.error)
            performance.refresh();
    }
    onViewStateChanged: {
        syncDrafts();
        Qt.callLater(refreshIfNeeded);
    }
    onInvestigatingChanged: {
        measure = "sales";
        Qt.callLater(resetScroll);
    }
    onAboutToShow: {
        syncDrafts();
        if (!viewState.current)
            performance.refresh();
    }
    Component.onCompleted: syncDrafts()

    Column {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        spacing: 12
        Text {
            width: parent.width
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: dialog.viewState.error || (dialog.viewState.busy ? "Preparando a análise dos produtos…" : !dialog.viewState.current ? "A análise será atualizada para o recorte selecionado." : "")
            visible: text.length > 0
            textFormat: Text.PlainText
            color: dialog.viewState.error ? Theme.danger : Theme.muted
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        ColumnLayout {
            width: parent.width
            visible: !dialog.investigating
            Layout.fillWidth: true
            Layout.fillHeight: false
            Layout.minimumWidth: 0
            spacing: 14
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "Compare produtos da mesma unidade e investigue sua evolução mensal. As opções desta lista não alteram os filtros do estoque."
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }
            GridLayout {
                objectName: "stockPerformanceInputs"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                columns: width >= 640 ? 3 : 1
                columnSpacing: 12
                rowSpacing: 10
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 5
                    Text {
                        objectName: "stockPerformanceUnitLabel"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: "Unidade de medida"
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    AppCombo {
                        objectName: "stockPerformanceUnit"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        model: dialog.units
                        currentIndex: dialog.optionIndex(model, dialog.draftUnit)
                        enabled: dialog.controlsEnabled && !dialog.viewState.busy && count > 0
                        Accessible.name: "Unidade do desempenho dos produtos"
                        onActivated: index => dialog.draftUnit = String(model[index].value)
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 5
                    Text {
                        objectName: "stockPerformanceWindowLabel"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: "Janela de comparação"
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    AppCombo {
                        objectName: "stockPerformanceWindow"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        model: dialog.windows
                        currentIndex: dialog.optionIndex(model, dialog.draftWindow)
                        enabled: dialog.controlsEnabled && !dialog.viewState.busy && count > 0
                        Accessible.name: "Quantidade de meses por janela de vendas"
                        onActivated: index => dialog.draftWindow = String(model[index].value)
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 5
                    Text {
                        objectName: "stockPerformanceSortLabel"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: "Ordenar por"
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    AppCombo {
                        objectName: "stockPerformanceSort"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        model: dialog.sorts
                        currentIndex: dialog.optionIndex(model, dialog.sortOption(dialog.draftSort))
                        enabled: dialog.controlsEnabled && !dialog.viewState.busy
                        Accessible.name: "Ordenação do desempenho dos produtos"
                        onActivated: index => dialog.chooseSort(String(model[index].value))
                    }
                }
            }
            ActionButton {
                objectName: "stockPerformanceDirection"
                visible: dialog.directionAvailable
                Layout.minimumWidth: 0
                Layout.fillWidth: parent.width < 500
                text: dialog.directionLabel
                enabled: dialog.controlsEnabled && !dialog.viewState.busy && dialog.directionAvailable
                Accessible.name: "Direção da ordenação dos produtos: " + dialog.directionLabel
                Accessible.description: dialog.directionAvailable ? "Inverte a ordem do indicador escolhido. Use Aplicar para atualizar a lista." : "Este ranking tem direção própria; escolha um indicador para inverter a ordem."
                onClicked: dialog.reverseDirection()
            }
            GridLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                columns: width >= 500 ? 2 : 1
                columnSpacing: 12
                rowSpacing: 10
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 5
                    Text {
                        objectName: "stockPerformanceSearchLabel"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: "Buscar nesta lista"
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    TextField {
                        id: search
                        objectName: "stockPerformanceSearch"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        implicitWidth: 0
                        implicitHeight: 42
                        text: dialog.draftQuery
                        placeholderText: "Código ou nome do produto"
                        maximumLength: 200
                        selectByMouse: true
                        font.pixelSize: 13
                        color: Theme.text
                        placeholderTextColor: Theme.muted
                        leftPadding: 12
                        rightPadding: 12
                        enabled: dialog.controlsEnabled && !dialog.viewState.busy
                        Accessible.name: "Buscar produto na lista de desempenho"
                        Accessible.description: "Digite o código ou nome e use Aplicar para atualizar a lista."
                        onTextEdited: dialog.draftQuery = text
                        background: Rectangle {
                            radius: 7
                            color: Theme.surface
                            border.color: search.activeFocus ? Theme.accent : Theme.line
                            border.width: search.activeFocus ? 2 : 1
                        }
                    }
                }
                ActionButton {
                    objectName: "stockPerformanceApply"
                    Layout.fillWidth: parent.columns === 1
                    Layout.minimumWidth: 0
                    Layout.alignment: Qt.AlignBottom
                    text: "Aplicar"
                    primary: true
                    enabled: dialog.controlsEnabled && !dialog.viewState.busy && dialog.validChoice
                    Accessible.name: "Aplicar opções e busca do desempenho dos produtos"
                    onClicked: dialog.applyChoice()
                }
            }
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                visible: dialog.unapplied
                text: "Há escolhas ainda não aplicadas. Os resultados abaixo mantêm a última escolha aplicada."
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
            Text {
                objectName: "stockPerformanceScope"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: [dialog.summary.comparisonLabel || dialog.summary.periodLabel, dialog.summary.orderLabel].filter(Boolean).join("\n")
                visible: text.length > 0
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }
            Text {
                objectName: "stockPerformanceReason"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: dialog.criticalReason
                visible: text.length > 0
                textFormat: Text.PlainText
                color: Theme.text
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }
            ActionButton {
                objectName: "stockPerformanceContextToggle"
                Layout.minimumWidth: 0
                Layout.fillWidth: parent.width < 500
                text: "Contexto e critérios"
                checkable: true
                checked: dialog.contextExpanded
                visible: Boolean(dialog.summary.scope || dialog.contextNotice)
                Accessible.name: "Contexto e critérios do desempenho dos produtos"
                Accessible.description: "Mostra ou recolhe filiais, escopo e critérios da comparação."
                onClicked: dialog.contextExpanded = checked
            }
            Text {
                objectName: "stockPerformanceContext"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: [dialog.summary.scope, dialog.contextNotice].filter(Boolean).join("\n")
                visible: dialog.contextExpanded && text.length > 0
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }
            ColumnLayout {
                objectName: "stockPerformanceRows"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 6
                Repeater {
                    id: productRows
                    model: dialog.summary.rows || []
                    Button {
                        id: product
                        required property var modelData
                        required property int index
                        objectName: "stockPerformanceRow" + index
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        implicitWidth: 0
                        implicitHeight: rowContent.implicitHeight + topPadding + bottomPadding
                        padding: 12
                        hoverEnabled: true
                        enabled: dialog.canInspect
                        Accessible.name: modelData.code + ". " + modelData.name + ". " + (modelData.sortValue ? modelData.sortLabel + ": " + modelData.sortValue + ". " : "") + "Vendas: " + modelData.sold + ". Evolução: " + modelData.evolution + ". Giro da fonte, mediana: " + modelData.turnover + ". " + (modelData.status || "") + ". Investigar produto."
                        onClicked: {
                            dialog.inspectedCode = modelData.code;
                            dialog.inspectedUnit = modelData.unit;
                            dialog.performance.investigate(modelData.code, modelData.unit);
                        }
                        background: Rectangle {
                            radius: 8
                            color: product.hovered ? Theme.hover : product.index % 2 === 0 ? Theme.subtle : Theme.surface
                            border.color: product.visualFocus ? Theme.accent : Theme.softLine
                        }
                        contentItem: ColumnLayout {
                            id: rowContent
                            spacing: 7
                            Text {
                                objectName: product.objectName + "Name"
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                text: product.modelData.code + " · " + product.modelData.name
                                textFormat: Text.PlainText
                                color: Theme.text
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                objectName: product.objectName + "Value"
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                text: product.modelData.sortValue ? product.modelData.sortLabel + ": " + product.modelData.sortValue : "Vendas: " + (product.modelData.sold || "—") + " · Evolução: " + (product.modelData.evolution || "—") + " · Giro da fonte (mediana): " + (product.modelData.turnover || "—")
                                textFormat: Text.PlainText
                                color: Theme.text
                                font.pixelSize: 12
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                objectName: product.objectName + "Detail"
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                text: [product.modelData.sortValue ? "Vendas: " + (product.modelData.sold || "—") : "", product.modelData.sortField === "stockQuantity" ? "" : product.modelData.stock, product.modelData.status].filter(Boolean).join(" · ")
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
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    visible: !(dialog.summary.rows || []).length && !dialog.viewState.busy
                    text: "Nenhum produto encontrado nesta unidade e busca. Ajuste as opções e aplique novamente."
                    color: Theme.muted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: (dialog.viewState.count || 0) + " produtos · Selecione um produto para investigar os meses e os sinais observados."
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
            GridLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                columns: width >= 360 ? 3 : 1
                columnSpacing: 10
                rowSpacing: 8
                ActionButton {
                    objectName: "stockPerformancePrevious"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: "Anterior"
                    iconName: "left"
                    enabled: dialog.canInspect && dialog.viewState.page > 1
                    Accessible.name: "Página anterior dos produtos"
                    onClicked: dialog.performance.setPage(dialog.viewState.page - 1)
                }
                Text {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: "Página " + (dialog.viewState.page || 1) + " de " + (dialog.viewState.pages || 1)
                    textFormat: Text.PlainText
                    color: Theme.muted
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
                ActionButton {
                    objectName: "stockPerformanceNext"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: "Próxima"
                    iconName: "right"
                    enabled: dialog.canInspect && dialog.viewState.page < dialog.viewState.pages
                    Accessible.name: "Próxima página dos produtos"
                    onClicked: dialog.performance.setPage(dialog.viewState.page + 1)
                }
            }
        }
        GridLayout {
            width: parent.width
            visible: dialog.investigating
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            columns: width >= 600 ? 2 : 1
            Layout.fillHeight: false
            columnSpacing: 12
            rowSpacing: 10
            ActionButton {
                objectName: "stockPerformanceBack"
                Layout.fillWidth: parent.columns === 1
                Layout.minimumWidth: 0
                text: "Voltar à lista"
                iconName: "left"
                onClicked: dialog.returnToList()
            }
            ActionButton {
                objectName: "stockPerformanceFilter"
                Layout.fillWidth: parent.columns === 1
                Layout.minimumWidth: 0
                text: "Filtrar este produto"
                iconName: "filter"
                enabled: dialog.canInspect
                onClicked: {
                    dialog.productFocusRequested(dialog.detail.code, dialog.detail.unit);
                    dialog.close();
                }
            }
        }
        Text {
            objectName: "stockPerformanceProduct"
            width: parent.width
            visible: dialog.investigating
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: (dialog.detail.code || "") + " · " + (dialog.detail.name || "")
            textFormat: Text.PlainText
            color: Theme.text
            font.pixelSize: 17
            font.weight: Font.DemiBold
            wrapMode: Text.WordWrap
        }
        Text {
            width: parent.width
            visible: dialog.investigating
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: [dialog.detail.unit, dialog.detail.scope].filter(Boolean).join(" · ")
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        Grid {
            id: metricsGrid
            readonly property real cardHeight: {
                let maximum = 0;
                for (const item of children)
                    if (item.objectName.indexOf("stockPerformanceMetric") === 0)
                        maximum = Math.max(maximum, item.implicitHeight);
                return maximum;
            }
            width: parent.width
            visible: dialog.investigating
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            columns: width >= 720 ? 4 : width >= 430 ? 2 : 1
            Layout.fillHeight: false
            spacing: 10
            Repeater {
                model: dialog.detail.metrics || []
                Rectangle {
                    id: metricCard
                    required property var modelData
                    required property int index
                    objectName: "stockPerformanceMetric" + index
                    width: (metricsGrid.width - (metricsGrid.columns - 1) * metricsGrid.spacing) / metricsGrid.columns
                    height: metricsGrid.columns > 1 ? Math.max(implicitHeight, metricsGrid.cardHeight) : implicitHeight
                    implicitHeight: metricContent.implicitHeight + 24
                    radius: 8
                    color: Theme.subtle
                    border.color: Theme.softLine
                    Column {
                        id: metricContent
                        x: 12
                        y: 12
                        width: parent.width - 24
                        spacing: 6
                        Text {
                            width: parent.width
                            text: metricCard.modelData.label || ""
                            textFormat: Text.PlainText
                            color: Theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            width: parent.width
                            text: metricCard.modelData.value || "—"
                            textFormat: Text.PlainText
                            color: Theme.text
                            font.pixelSize: 20
                            font.weight: Font.DemiBold
                            wrapMode: Text.WrapAnywhere
                        }
                        Text {
                            width: parent.width
                            text: metricCard.modelData.detail || ""
                            visible: text.length > 0
                            textFormat: Text.PlainText
                            color: Theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }
        AppCombo {
            objectName: "stockPerformanceMeasure"
            width: parent.width
            visible: dialog.investigating
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            model: dialog.seriesKinds
            currentIndex: dialog.optionIndex(model, dialog.effectiveMeasure)
            enabled: dialog.canInspect && count > 0
            Accessible.name: "Indicador mensal do desempenho do produto"
            onActivated: index => dialog.measure = String(model[index].value)
        }
        ColumnLayout {
            id: chartGroup
            width: parent.width
            visible: dialog.investigating
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.fillHeight: false
            spacing: 10
            StockPlot {
                id: plot
                objectName: "stockPerformanceChart"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.preferredHeight: Math.max(110, Math.min(230, dialog.height - 240 - readout.implicitHeight))
                points: dialog.series.points || []
                unit: dialog.series.unit || ""
                seriesName: dialog.series.title || "Evolução mensal do produto"
                mode: dialog.effectiveMeasure === "sales" ? "column" : "line"
                movingAverage: false
                precision: 2
                enabled: dialog.canInspect
                onPointsChanged: selectedIndex = -1
                onActiveFocusChanged: if (activeFocus)
                    Qt.callLater(() => dialog.reveal(chartGroup))
                onReadoutChanged: if (activeFocus)
                    Qt.callLater(() => dialog.reveal(chartGroup))
            }
            Text {
                id: readout
                objectName: "stockPerformanceReadout"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: plot.readout || "Selecione um mês com o cursor ou as setas para consultar o valor. Meses sem dados permanecem em branco."
                textFormat: Text.PlainText
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
        }
        Text {
            width: parent.width
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: dialog.series.note || ""
            visible: dialog.investigating && text.length > 0
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        Repeater {
            model: [
                {
                    key: "Evidence",
                    title: "O que os dados mostram",
                    rows: dialog.detail.evidence || []
                },
                {
                    key: "Hypotheses",
                    title: "Hipóteses a verificar",
                    rows: dialog.detail.hypotheses || []
                },
                {
                    key: "Limitations",
                    title: "Limites desta análise",
                    rows: dialog.detail.limitations || []
                }
            ]
            ColumnLayout {
                id: findings
                width: parent.width
                required property var modelData
                objectName: "stockPerformance" + modelData.key
                visible: dialog.investigating && modelData.rows.length > 0
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.fillHeight: false
                spacing: 7
                Text {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: findings.modelData.title
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }
                Repeater {
                    model: findings.modelData.rows
                    Text {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: "• " + modelData
                        textFormat: Text.PlainText
                        color: Theme.muted
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }
}
