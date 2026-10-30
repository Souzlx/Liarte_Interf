pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "stockPrioritiesSection"
    required property var priorities
    property bool controlsEnabled: true
    readonly property var viewState: priorities.state || ({})
    readonly property var summary: priorities.summary || ({})
    readonly property var detail: priorities.detail || ({})
    readonly property bool canInspect: controlsEnabled && viewState.current === true && !viewState.busy
    readonly property bool modalOpen: categoryChoice.popup.visible || unitChoice.popup.visible || windowChoice.popup.visible || priorityDetail.visible
    property alias detailDialog: priorityDetail
    property string draftCategory: "review"
    property string draftUnit: ""
    property string draftWindow: "3"
    property string draftQuery: ""
    property string syncedChoice: ""
    property bool contextExpanded: false
    property bool detailRequested: false
    property string inspectedCode: ""
    property string inspectedUnit: ""
    readonly property var units: viewState.units || []
    readonly property var windows: viewState.windows || []
    readonly property var categories: (viewState.categories || []).map(item => ({value: item.value, label: item.label + " (" + item.count + ")"}))
    readonly property bool validChoice: units.some(item => String(item.value) === draftUnit) && windows.some(item => String(item.value) === draftWindow)
    readonly property bool unapplied: choice(draftUnit, draftWindow, draftCategory, draftQuery) !== choice(viewState.unit, viewState.window, viewState.category, viewState.query)
    signal positionsRequested(string code, string unit)
    signal performanceRequested(string code, string unit, int window)
    signal performanceListRequested

    Layout.fillWidth: true
    Layout.minimumWidth: 0
    spacing: 12

    function choice(unit, window, category, query) {
        return JSON.stringify([String(unit || ""), String(window || "3"), String(category || "review"), String(query || "")]);
    }
    function optionIndex(options, value) {
        return Math.max(0, options.findIndex(item => String(item.value) === String(value)));
    }
    function syncDrafts() {
        const applied = choice(viewState.unit, viewState.window, viewState.category, viewState.query);
        if (!syncedChoice || choice(draftUnit, draftWindow, draftCategory, draftQuery) === syncedChoice) {
            draftUnit = String(viewState.unit || "");
            draftWindow = String(viewState.window || "3");
            draftCategory = String(viewState.category || "review");
            draftQuery = String(viewState.query || "");
        }
        if (!units.some(item => String(item.value) === draftUnit))
            draftUnit = units.length ? String(units[0].value) : "";
        syncedChoice = applied;
    }
    function refreshIfNeeded() {
        if (visible && viewState.available && !viewState.current && !viewState.busy && !viewState.error && !viewState.cancelled)
            priorities.refresh();
    }
    function applyChoice() {
        if (controlsEnabled && !viewState.busy && validChoice)
            priorities.configure(draftUnit, Number(draftWindow), draftCategory, draftQuery);
    }
    function inspect(row) {
        if (!canInspect)
            return;
        inspectedCode = row.code;
        inspectedUnit = row.unit;
        detailRequested = true;
        priorities.investigate(row.code, row.unit);
        openRequestedDetail();
    }
    function openRequestedDetail() {
        if (detailRequested && canInspect && detail.code === inspectedCode && detail.unit === inspectedUnit) {
            detailRequested = false;
            priorityDetail.open();
        }
    }
    onViewStateChanged: {
        syncDrafts();
        Qt.callLater(refreshIfNeeded);
        Qt.callLater(openRequestedDetail);
    }
    onDetailChanged: {
        if (!detail.code)
            priorityDetail.close();
        else
            Qt.callLater(openRequestedDetail);
    }
    onVisibleChanged: {
        if (visible)
            Qt.callLater(refreshIfNeeded);
        else {
            detailRequested = false;
            priorityDetail.close();
        }
    }
    Component.onCompleted: {
        syncDrafts();
        Qt.callLater(refreshIfNeeded);
    }

    GridLayout {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        columns: width >= Math.max(620, performanceAction.naturalWidth + 300) ? 2 : 1
        rowSpacing: 8
        columnSpacing: 12
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: 4
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "Prioridades dos produtos"
                color: Theme.text
                font.pixelSize: 18
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "Comece pelas situações que pedem revisão. Selecione um produto para entender os motivos."
                color: Theme.muted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }
        }
        ActionButton {
            id: performanceAction
            objectName: "stockPrioritiesPerformanceList"
            Layout.fillWidth: parent.columns === 1
            Layout.minimumWidth: 0
            text: "Desempenho completo"
            iconName: "chart"
            enabled: root.controlsEnabled && !root.viewState.busy
            onClicked: root.performanceListRequested()
        }
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        implicitHeight: choices.implicitHeight + 24
        color: Theme.surface
        border.color: Theme.softLine
        radius: Theme.radius
        ColumnLayout {
            id: choices
            x: 12
            y: 12
            width: parent.width - 24
            spacing: 10
            GridLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                columns: width >= 620 ? 3 : width >= 360 ? 2 : 1
                columnSpacing: 10
                rowSpacing: 8
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 4
                    Text { text: "Foco da revisão"; color: Theme.muted; font.pixelSize: 11 }
                    AppCombo {
                        id: categoryChoice
                        objectName: "stockPrioritiesCategory"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        model: root.categories
                        currentIndex: root.optionIndex(model, root.draftCategory)
                        enabled: root.controlsEnabled && !root.viewState.busy && count > 0
                        Accessible.name: "Foco da revisão dos produtos"
                        onActivated: index => root.draftCategory = String(model[index].value)
                        ToolTip.visible: hovered
                        ToolTip.text: currentText
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 4
                    Text { text: "Unidade"; color: Theme.muted; font.pixelSize: 11 }
                    AppCombo {
                        id: unitChoice
                        objectName: "stockPrioritiesUnit"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        model: root.units
                        currentIndex: root.optionIndex(model, root.draftUnit)
                        enabled: root.controlsEnabled && !root.viewState.busy && count > 0
                        Accessible.name: "Unidade das prioridades dos produtos"
                        onActivated: index => root.draftUnit = String(model[index].value)
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 4
                    Text { text: "Janela de vendas"; color: Theme.muted; font.pixelSize: 11 }
                    AppCombo {
                        id: windowChoice
                        objectName: "stockPrioritiesWindow"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        model: root.windows
                        currentIndex: root.optionIndex(model, root.draftWindow)
                        enabled: root.controlsEnabled && !root.viewState.busy && count > 0
                        Accessible.name: "Janela de vendas das prioridades"
                        onActivated: index => root.draftWindow = String(model[index].value)
                    }
                }
            }
            GridLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                columns: width >= 360 ? 2 : 1
                columnSpacing: 10
                rowSpacing: 8
                TextField {
                    id: search
                    objectName: "stockPrioritiesSearch"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    implicitWidth: 0
                    implicitHeight: 42
                    text: root.draftQuery
                    placeholderText: "Buscar código ou produto"
                    maximumLength: 200
                    selectByMouse: true
                    font.pixelSize: 13
                    color: Theme.text
                    placeholderTextColor: Theme.muted
                    leftPadding: 12
                    rightPadding: 12
                    enabled: root.controlsEnabled && !root.viewState.busy
                    Accessible.name: "Buscar na lista de prioridades"
                    Accessible.description: "Digite o código ou nome e use Aplicar. Os filtros gerais do estoque são preservados."
                    onTextEdited: root.draftQuery = text
                    onAccepted: root.applyChoice()
                    background: Rectangle {
                        radius: 7
                        color: Theme.surface
                        border.color: search.activeFocus ? Theme.accent : Theme.line
                        border.width: search.activeFocus ? 2 : 1
                    }
                }
                ActionButton {
                    objectName: "stockPrioritiesApply"
                    Layout.fillWidth: parent.columns === 1
                    Layout.minimumWidth: 0
                    text: "Aplicar"
                    primary: true
                    enabled: root.controlsEnabled && !root.viewState.busy && root.validChoice
                    Accessible.name: "Aplicar foco, unidade, janela e busca das prioridades"
                    onClicked: root.applyChoice()
                }
            }
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                visible: root.unapplied
                text: "Há escolhas ainda não aplicadas. A lista mantém o recorte indicado abaixo."
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        Text {
            objectName: "stockPrioritiesPeriod"
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: root.summary.closingLabel ? "Fechamento: " + root.summary.closingLabel + " · vendas: " + root.summary.targetLabel : "Aguardando a análise do recorte."
            textFormat: Text.PlainText
            color: Theme.text
            font.pixelSize: 12
            font.weight: Font.DemiBold
            wrapMode: Text.WordWrap
        }
        ActionButton {
            objectName: "stockPrioritiesContextToggle"
            text: root.contextExpanded ? "Menos" : "Critérios"
            subtle: true
            implicitWidth: Math.max(82, naturalWidth)
            enabled: root.viewState.current
            Accessible.name: root.contextExpanded ? "Recolher critérios das prioridades" : "Mostrar critérios das prioridades"
            onClicked: root.contextExpanded = !root.contextExpanded
        }
    }
    Text {
        objectName: "stockPrioritiesReference"
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        text: root.summary.referenceNotice || "Saldo e capital referem-se ao fechamento indicado, não ao saldo atual da base."
        visible: root.viewState.current
        textFormat: Text.PlainText
        color: Theme.muted
        font.pixelSize: 11
        wrapMode: Text.WordWrap
    }
    Text {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        visible: root.contextExpanded && root.viewState.current
        text: [root.summary.scope || "", root.summary.notice || "", "Ordenação: " + (root.summary.orderLabel || "Maior capital no fechamento") + ". Capital é custo, não faturamento. Cobertura não mede a idade dos lotes."].filter(value => value.length > 0).join("\n")
        textFormat: Text.PlainText
        color: Theme.muted
        font.pixelSize: 11
        wrapMode: Text.WordWrap
    }
    Text {
        objectName: "stockPrioritiesNotice"
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        text: root.viewState.error || (root.viewState.busy ? "Preparando as prioridades dos produtos…" : root.viewState.cancelled ? (root.viewState.current ? "Atualização cancelada. Os resultados anteriores foram mantidos." : "A preparação das prioridades foi cancelada.") : root.summary.reason || "")
        visible: text.length > 0
        textFormat: Text.PlainText
        color: root.viewState.error ? Theme.danger : Theme.muted
        font.pixelSize: 12
        wrapMode: Text.WordWrap
    }
    ActionButton {
        objectName: "stockPrioritiesRefresh"
        visible: root.viewState.available && !root.viewState.current && !root.viewState.busy
        text: root.viewState.error ? "Tentar novamente" : "Preparar prioridades"
        primary: true
        enabled: root.controlsEnabled
        onClicked: root.priorities.refresh()
    }
    ActionButton {
        objectName: "stockPrioritiesCancel"
        visible: root.viewState.busy
        text: "Cancelar análise"
        subtle: true
        onClicked: root.priorities.cancel()
    }
    Repeater {
        id: productRows
        model: root.summary.rows || []
        Button {
            id: productRow
            required property var modelData
            required property int index
            objectName: "stockPrioritiesRow_" + index
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            implicitHeight: implicitContentHeight + topPadding + bottomPadding
            leftPadding: 14
            rightPadding: 14
            topPadding: 12
            bottomPadding: 12
            enabled: root.canInspect
            hoverEnabled: true
            Accessible.name: modelData.code + " · " + modelData.name + " · " + modelData.unit + ". " + modelData.primaryTitle + ". Investigar produto."
            onClicked: root.inspect(modelData)
            contentItem: ColumnLayout {
                spacing: 7
                GridLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    columns: width >= 620 ? 3 : 1
                    columnSpacing: 18
                    rowSpacing: 5
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        spacing: 3
                        Text {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: productRow.modelData.code + " · " + productRow.modelData.name
                            textFormat: Text.PlainText
                            color: Theme.text
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: productRow.modelData.primaryTitle + " · " + productRow.modelData.unit
                            textFormat: Text.PlainText
                            color: Theme.accent
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: "Estoque a custo\n" + productRow.modelData.stockCost
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: "Vendas líquidas\n" + productRow.modelData.sold
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                }
                Text {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: productRow.modelData.reason
                    textFormat: Text.PlainText
                    color: Theme.muted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
                Text {
                    text: "Investigar produto →"
                    textFormat: Text.PlainText
                    color: Theme.accent
                    font.pixelSize: 11
                }
            }
            background: Rectangle {
                color: productRow.hovered || productRow.activeFocus ? Theme.selected : Theme.surface
                radius: Theme.radius
                border.color: productRow.visualFocus ? Theme.accent : Theme.line
                border.width: productRow.visualFocus ? 2 : 1
            }
        }
    }
    Text {
        objectName: "stockPrioritiesEmpty"
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        visible: root.viewState.current && !root.viewState.busy && root.viewState.count === 0
        text: "Nenhum produto atende ao foco aplicado. Escolha outro foco ou refine a unidade e o período. Dados indisponíveis não são tratados como zero."
        color: Theme.muted
        font.pixelSize: 12
        wrapMode: Text.WordWrap
    }
    RowLayout {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        Text {
            objectName: "stockPrioritiesCount"
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: (root.viewState.count || 0) + " produtos · " + (root.summary.orderLabel || "Maior capital no fechamento")
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        ActionButton {
            objectName: "stockPrioritiesPrevious"
            text: ""
            iconName: "left"
            implicitWidth: 40
            enabled: root.canInspect && root.viewState.page > 1
            Accessible.name: "Página anterior das prioridades"
            onClicked: root.priorities.setPage(root.viewState.page - 1)
        }
        Text {
            text: (root.viewState.page || 1) + " / " + (root.viewState.pages || 1)
            color: Theme.text
            font.pixelSize: 12
        }
        ActionButton {
            objectName: "stockPrioritiesNext"
            text: ""
            iconName: "right"
            implicitWidth: 40
            enabled: root.canInspect && root.viewState.page < root.viewState.pages
            Accessible.name: "Próxima página das prioridades"
            onClicked: root.priorities.setPage(root.viewState.page + 1)
        }
    }
    AppDialog {
        id: priorityDetail
        objectName: "stockPrioritiesDetail"
        title: "Investigar prioridade"
        width: Math.min(780, parent ? parent.width - 32 : 780)
        height: Math.min(720, parent ? parent.height - 32 : 720)
        onClosed: root.detailRequested = false
        Text {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: (root.detail.code || "") + " · " + (root.detail.name || "")
            textFormat: Text.PlainText
            color: Theme.text
            font.pixelSize: 17
            font.weight: Font.DemiBold
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: root.detail.title || ""
            textFormat: Text.PlainText
            color: Theme.accent
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        GridLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            columns: width >= 520 ? 2 : 1
            columnSpacing: 16
            rowSpacing: 12
            Repeater {
                model: root.detail.metrics || []
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 3
                    Text {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: modelData.label
                        textFormat: Text.PlainText
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: modelData.value
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: modelData.detail || ""
                        textFormat: Text.PlainText
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
        Repeater {
            model: root.detail.reasons || []
            ColumnLayout {
                required property var modelData
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 5
                Text {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: modelData.title
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }
                Text {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: modelData.fact
                    textFormat: Text.PlainText
                    color: Theme.muted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
                Text {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: "Próximo passo: " + modelData.nextStep
                    textFormat: Text.PlainText
                    color: Theme.muted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }
        }
        Text {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: root.detail.notice || ""
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        GridLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            columns: width >= 460 ? 2 : 1
            rowSpacing: 8
            columnSpacing: 10
            ActionButton {
                objectName: "stockPrioritiesViewPositions"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "Ver posições"
                enabled: root.canInspect && Boolean(root.detail.code)
                onClicked: {
                    const code = root.detail.code;
                    const unit = root.detail.unit;
                    priorityDetail.close();
                    root.positionsRequested(code, unit);
                }
            }
            ActionButton {
                objectName: "stockPrioritiesHistory"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "Histórico completo"
                primary: true
                iconName: "chart"
                enabled: root.canInspect && Boolean(root.detail.code)
                onClicked: {
                    const code = root.detail.code;
                    const unit = root.detail.unit;
                    const window = Number(root.viewState.window);
                    priorityDetail.close();
                    root.performanceRequested(code, unit, window);
                }
            }
        }
    }
}
