import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "components" as Ui

FocusScope {
    id: page
    objectName: "inventoryWorkspace"
    required property var hostWindow
    readonly property var state: inventory.state
    readonly property var view: inventory.analysis
    readonly property var detail: inventory.detail
    readonly property var backupState: inventory.backupState
    property bool advanced: false
    readonly property bool modalOpen: sourceDialog.visible || saveStockDialog.visible || stockDetail.visible || stockMethodology.visible || stockChartDialog.visible || stockBackups.visible || confirmStockRestore.visible || monthlySection.modalOpen
    readonly property bool controlsEnabled: state.loaded && state.task !== "load" && state.task !== "export"
    readonly property string activeSection: scroll.contentY >= positionsSection.y - 80 || scroll.contentHeight > scroll.height && scroll.atYEnd ? "products" : scroll.contentY >= monthlySection.y - 80 ? "monthly" : "overview"
    property var lastFocusedControl: null

    function visibleControl(item) {
        if (!item || !item.visible || !item.enabled || item.width <= 0 || item.height <= 0)
            return false;
        const position = item.mapToItem(scroll, 0, 0);
        return position.x >= -1 && position.x + item.width <= scroll.width + 1 && position.y >= -1 && position.y + item.height <= scroll.height + 1;
    }
    function firstVisibleControl(parentItem) {
        for (const item of parentItem.children) {
            if (!item.visible || !item.enabled)
                continue;
            if (item.activeFocusOnTab && visibleControl(item))
                return item;
            const child = firstVisibleControl(item);
            if (child)
                return child;
        }
        return null;
    }
    function navigate(section) {
        const maximum = Math.max(0, scroll.contentHeight - scroll.height);
        const destination = section === "products" ? Math.min(maximum, positionsSection.y - 18) : section === "monthly" ? Math.min(maximum, monthlySection.y - 18) : 0;
        stockScrollMotion.stop();
        if (Ui.Theme.motionEnabled) {
            stockScrollMotion.to = destination;
            stockScrollMotion.restart();
        } else
            scroll.contentY = destination;
        if (section === "products")
            stockTable.forceActiveFocus();
    }
    function restoreFocus() {
        const item = visibleControl(lastFocusedControl) ? lastFocusedControl : firstVisibleControl(content);
        if (item)
            item.forceActiveFocus(Qt.TabFocusReason);
        else
            page.forceActiveFocus();
    }
    Connections {
        target: page.hostWindow
        function onActiveFocusItemChanged() {
            if (!page.visible || page.modalOpen)
                return;
            const item = page.hostWindow.activeFocusItem;
            for (let ancestor = item; ancestor; ancestor = ancestor.parent) {
                if (ancestor === content) {
                    page.lastFocusedControl = item;
                    return;
                }
            }
        }
    }
    Shortcut {
        sequence: "Ctrl+F"
        enabled: page.visible && page.state.loaded && !page.modalOpen && !hostWindow.globalModalOpen
        onActivated: {
            page.navigate("overview");
            stockSearch.focusSearch();
        }
    }
    NumberAnimation {
        id: stockScrollMotion
        target: scroll
        property: "contentY"
        duration: Ui.Theme.motion
        easing.type: Easing.OutCubic
    }
    onVisibleChanged: if (!visible)
        stockScrollMotion.stop()
    Connections {
        target: Ui.Theme
        function onMotionEnabledChanged() {
            if (!Ui.Theme.motionEnabled)
                stockScrollMotion.complete();
        }
    }
    Flickable {
        id: scroll
        objectName: "stockScroll"
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight + 48
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }
        ColumnLayout {
            id: content
            x: page.width < 600 ? 16 : 28
            y: 22
            width: scroll.width - 2 * x
            spacing: 18
            GridLayout {
                Layout.fillWidth: true
                columns: page.width < 720 ? 1 : 2
                rowSpacing: 12
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Text {
                        Layout.fillWidth: true
                        text: page.state.loaded ? "Saldo atual · " + page.state.asOf : "Estoque e rotatividade"
                        textFormat: Text.PlainText
                        color: Ui.Theme.text
                        font.pixelSize: page.width < 600 ? 21 : 25
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        Layout.fillWidth: true
                        text: page.state.loaded ? "Panorama atual e investigação mensal de estoque e vendas" : "Preparando a base de estoque da LIARTE."
                        textFormat: Text.PlainText
                        color: Ui.Theme.muted
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                }
                GridLayout {
                    id: stockHeaderActions
                    objectName: "stockHeaderActions"
                    Layout.alignment: Qt.AlignRight
                    Layout.fillWidth: page.width < 720
                    Layout.minimumWidth: 0
                    columns: page.width < 720 ? 2 : 4
                    columnSpacing: 8
                    rowSpacing: 8
                    Ui.ActionButton {
                        id: openBase
                        objectName: "openStockBase"
                        text: page.state.loaded ? "Atualizar base" : "Abrir base"
                        iconName: "folder"
                        primary: !page.state.loaded
                        Layout.fillWidth: stockHeaderActions.columns === 2
                        Layout.minimumWidth: 0
                        enabled: !page.state.busy
                        onClicked: sourceDialog.open()
                    }
                    Ui.ActionButton {
                        objectName: "stockExportButton"
                        visible: page.state.loaded
                        text: "Baixar Excel"
                        iconName: "download"
                        Layout.fillWidth: stockHeaderActions.columns === 2
                        Layout.minimumWidth: 0
                        enabled: !page.state.busy && page.state.current
                        onClicked: saveStockDialog.open()
                    }
                    Ui.ActionButton {
                        objectName: "stockRestoreButton"
                        text: page.width < 600 ? "" : "Restaurar"
                        iconName: "refresh"
                        implicitWidth: page.width < 600 ? 40 : Math.max(100, naturalWidth)
                        enabled: page.backupState.available && !page.state.busy
                        Accessible.name: "Restaurar base anterior"
                        onClicked: stockBackups.open()
                        ToolTip.visible: hovered
                        ToolTip.text: page.backupState.available ? "Restaurar base anterior" : "As bases anteriores ficam disponíveis após atualizar a base neste computador."
                    }
                    Ui.ActionButton {
                        objectName: "stockMethodologyButton"
                        text: ""
                        iconName: "info"
                        implicitWidth: 40
                        Accessible.name: "Como ler os indicadores de estoque"
                        onClicked: stockMethodology.open()
                        ToolTip.visible: hovered
                        ToolTip.text: "Como ler os indicadores"
                    }
                }
            }
            Rectangle {
                visible: page.state.error.length > 0
                Layout.fillWidth: true
                implicitHeight: errorText.implicitHeight + 26
                radius: 8
                color: Ui.Theme.warningBg
                Text {
                    id: errorText
                    x: 13
                    y: 13
                    width: parent.width - 26
                    text: page.state.error
                    textFormat: Text.PlainText
                    color: Ui.Theme.danger
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }
            ColumnLayout {
                visible: page.state.busy && page.state.task !== "analysis"
                Layout.fillWidth: true
                spacing: 6
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: page.state.busyLabel
                        textFormat: Text.PlainText
                        color: Ui.Theme.muted
                        font.pixelSize: 12
                    }
                    Ui.ActionButton {
                        text: "Cancelar"
                        subtle: true
                        onClicked: inventory.cancel()
                    }
                }
                ProgressBar {
                    Layout.fillWidth: true
                    from: 0
                    to: 100
                    value: page.state.progress
                    indeterminate: page.state.task !== "load"
                }
            }
            Rectangle {
                visible: !page.state.loaded && !page.state.busy
                Layout.fillWidth: true
                implicitHeight: 240
                color: Ui.Theme.surface
                radius: Ui.Theme.radius
                border.color: Ui.Theme.line
                ColumnLayout {
                    anchors.centerIn: parent
                    width: Math.min(420, parent.width - 44)
                    spacing: 14
                    Ui.Icon {
                        name: "box"
                        color: Ui.Theme.accent
                        Layout.preferredWidth: 36
                        Layout.preferredHeight: 36
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Decisões de estoque, em um só lugar."
                        textFormat: Text.PlainText
                        color: Ui.Theme.text
                        font.pixelSize: 20
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "A base integrada abre automaticamente. Para atualizar os dados, utilize um novo arquivo da empresa."
                        textFormat: Text.PlainText
                        color: Ui.Theme.muted
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                    }
                }
            }
            Rectangle {
                visible: page.state.loaded
                Layout.fillWidth: true
                implicitHeight: filterContent.implicitHeight + 32
                radius: Ui.Theme.radius
                color: Ui.Theme.surface
                border.color: Ui.Theme.softLine
                ColumnLayout {
                    id: filterContent
                    x: 16
                    y: 16
                    width: parent.width - 32
                    spacing: 14
                    enabled: page.controlsEnabled
                    GridLayout {
                        id: quickStockGrid
                        Layout.fillWidth: true
                        columns: page.width < 850 ? 2 : 4
                        columnSpacing: 12
                        rowSpacing: 12
                        ColumnLayout {
                            Layout.columnSpan: 2
                            Layout.preferredWidth: (quickStockGrid.width - (quickStockGrid.columns - 1) * 12) / quickStockGrid.columns * 2 + 12
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            spacing: 5
                            Text {
                                text: "Produto"
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                            }
                            Ui.StockSearch {
                                id: stockSearch
                                objectName: "stockProductSearch"
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                            }
                        }
                        Ui.StockFilter {
                            fieldKey: "branch"
                            Layout.preferredWidth: (quickStockGrid.width - (quickStockGrid.columns - 1) * 12) / quickStockGrid.columns
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                        }
                        Ui.StockFilter {
                            fieldKey: "warehouse"
                            Layout.preferredWidth: (quickStockGrid.width - (quickStockGrid.columns - 1) * 12) / quickStockGrid.columns
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                        }
                    }
                    GridLayout {
                        visible: page.advanced
                        Layout.fillWidth: true
                        columns: page.width < 700 ? 2 : 5
                        columnSpacing: 12
                        rowSpacing: 12
                        Ui.StockFilter {
                            fieldKey: "group"
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                        }
                        Ui.StockFilter {
                            fieldKey: "kind"
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                        }
                        Ui.StockFilter {
                            fieldKey: "abc"
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                        }
                        Ui.StockFilter {
                            fieldKey: "activity"
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                        }
                        Ui.StockFilter {
                            fieldKey: "balance"
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                        }
                    }
                    GridLayout {
                        id: stockPeriodGrid
                        Layout.fillWidth: true
                        columns: page.width < 1050 ? 2 : 4
                        columnSpacing: 12
                        rowSpacing: 12
                        Ui.StockFilter {
                            fieldKey: "start"
                            Layout.preferredWidth: (stockPeriodGrid.width - (stockPeriodGrid.columns - 1) * 12) / stockPeriodGrid.columns
                            title: "Histórico · mês inicial"
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                        }
                        Ui.StockFilter {
                            fieldKey: "end"
                            Layout.preferredWidth: (stockPeriodGrid.width - (stockPeriodGrid.columns - 1) * 12) / stockPeriodGrid.columns
                            title: "Histórico · mês final"
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                        }
                        Ui.StockFilter {
                            fieldKey: "unit"
                            Layout.preferredWidth: (stockPeriodGrid.width - (stockPeriodGrid.columns - 1) * 12) / stockPeriodGrid.columns
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                        }
                        RowLayout {
                            Layout.columnSpan: page.width < 650 ? 2 : 1
                            Layout.preferredWidth: (stockPeriodGrid.width - (stockPeriodGrid.columns - 1) * 12) / stockPeriodGrid.columns
                            Layout.minimumWidth: 0
                            Layout.alignment: Qt.AlignBottom
                            Layout.fillWidth: true
                            spacing: 4
                            Ui.ActionButton {
                                text: page.advanced ? "Menos filtros" : "Mais filtros"
                                iconName: "filter"
                                onClicked: page.advanced = !page.advanced
                            }
                            Ui.ActionButton {
                                text: "Limpar"
                                subtle: true
                                Accessible.name: "Limpar todos os filtros de estoque"
                                onClicked: inventory.resetFilters()
                            }
                        }
                    }
                }
            }
            GridLayout {
                visible: page.state.loaded
                Layout.fillWidth: true
                columns: page.width >= 1150 ? 5 : page.width >= 880 ? 6 : page.width >= 560 ? 2 : 1
                columnSpacing: 12
                rowSpacing: 12
                Repeater {
                    model: page.view.metrics
                    Ui.MetricCard {
                        required property var modelData
                        required property int index
                        objectName: "stockMetric" + index
                        Layout.columnSpan: page.width >= 880 && page.width < 1150 ? (index < 3 ? 2 : 3) : page.width >= 560 && page.width < 880 && index === 4 ? 2 : 1
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        metric: modelData
                        emphasized: index === 0
                        iconName: index === 0 ? "price" : "box"
                    }
                }
            }
            GridLayout {
                visible: page.state.loaded
                Layout.fillWidth: true
                columns: width >= 1080 ? 2 : 1
                columnSpacing: 16
                rowSpacing: 16
                Rectangle {
                    id: stockHistoryCard
                    objectName: "stockHistoryCard"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 0
                    Layout.preferredHeight: stockHistoryContent.implicitHeight + 36
                    color: Ui.Theme.surface
                    radius: Ui.Theme.radius
                    border.color: Ui.Theme.softLine
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
                                color: Ui.Theme.text
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                                wrapMode: Text.WordWrap
                            }
                            Ui.AppCombo {
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
                            Ui.ActionButton {
                                id: openStockChart
                                objectName: "openStockChart"
                                text: "Ampliar"
                                iconName: "chart"
                                implicitWidth: Math.max(112, naturalWidth)
                                Layout.minimumWidth: implicitWidth
                                font.pixelSize: 11
                                subtle: true
                                onClicked: stockChartDialog.open()
                            }
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            columns: width >= 460 ? 2 : 1
                            rowSpacing: 4
                            Text {
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                text: page.view.historySummary.value || "—"
                                color: Ui.Theme.text
                                font.pixelSize: 24
                                minimumPixelSize: 18
                                fontSizeMode: Text.HorizontalFit
                                font.weight: Font.DemiBold
                                textFormat: Text.PlainText
                                ToolTip.visible: summaryHover.hovered
                                ToolTip.text: page.view.historySummary.full || ""
                                HoverHandler {
                                    id: summaryHover
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: page.view.historySummary.change || ""
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                                textFormat: Text.PlainText
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: (page.view.historySummary.period || "") + " · " + page.view.historicalScope
                            textFormat: Text.PlainText
                            font.pixelSize: 11
                            color: Ui.Theme.muted
                            wrapMode: Text.WordWrap
                        }
                        Ui.StockPlot {
                            id: stockTrend
                            objectName: "stockTrend"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 220
                            Layout.preferredHeight: Math.min(330, Math.max(220, stockHistoryCard.width * 0.45))
                            points: page.view.plotTrend || []
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
                                    width: 16
                                    height: 3
                                    radius: 1
                                    color: Ui.Theme.accent
                                }
                                Text {
                                    text: "Custo"
                                    color: Ui.Theme.muted
                                    font.pixelSize: 11
                                }
                            }
                            Ui.StockToggle {
                                id: stockAverage
                                objectName: "stockAverage"
                                text: "Média 3m"
                                checked: true
                                font.pixelSize: 11
                                Accessible.name: "Exibir média móvel de três meses"
                            }
                            Ui.StockToggle {
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
                            color: Ui.Theme.subtle
                            Text {
                                id: stockTrendReadout
                                objectName: "stockTrendReadout"
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 10
                                text: stockTrend.readout || "Passe o cursor ou use as setas. Meses sem fechamento permanecem em branco."
                                textFormat: Text.PlainText
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
                Rectangle {
                    objectName: "stockCapitalCard"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 0
                    Layout.preferredHeight: stockCapitalContent.implicitHeight + 36
                    radius: Ui.Theme.radius
                    color: Ui.Theme.surface
                    border.color: Ui.Theme.softLine
                    ColumnLayout {
                        id: stockCapitalContent
                        anchors.fill: parent
                        anchors.margins: 18
                        spacing: 7
                        Text {
                            Layout.fillWidth: true
                            text: "Capital por produto"
                            color: Ui.Theme.text
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                        }
                        Text {
                            Layout.fillWidth: true
                            text: Math.min(8, page.view.ranking.length) + " maiores · custo e participação no capital positivo"
                            color: Ui.Theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        Ui.StockBars {
                            id: stockRanking
                            objectName: "stockRanking"
                            Layout.fillWidth: true
                            rows: page.view.ranking.slice(0, 8)
                            interactive: true
                            onSelected: code => inventory.setFilter("product", code)
                        }
                        Item {
                            Layout.fillHeight: true
                        }
                        Text {
                            Layout.fillWidth: true
                            text: stockRanking.rows.length ? "Acumulado: " + stockRanking.rows[stockRanking.rows.length - 1].cumulative + " · selecione um produto para analisar" : "Sem capital positivo no recorte"
                            color: Ui.Theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                            textFormat: Text.PlainText
                        }
                    }
                }
            }
            Rectangle {
                visible: page.state.loaded
                Layout.fillWidth: true
                implicitHeight: activityColumn.implicitHeight + 36
                radius: Ui.Theme.radius
                color: Ui.Theme.surface
                border.color: Ui.Theme.softLine
                ColumnLayout {
                    id: activityColumn
                    x: 18
                    y: 18
                    width: parent.width - 36
                    spacing: 12
                    Text {
                        text: "Capital positivo por última venda"
                        color: Ui.Theme.text
                        font.pixelSize: 15
                        font.weight: Font.DemiBold
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: page.width < 700 ? 2 : 4
                        columnSpacing: 12
                        rowSpacing: 12
                        Repeater {
                            model: page.view.activityChart
                            Button {
                                id: activityButton
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: 64
                                padding: 10
                                onClicked: inventory.setFilter("activity", modelData.name)
                                Accessible.name: modelData.name + ": " + modelData.display + ". Filtrar."
                                background: Rectangle {
                                    color: activityButton.hovered ? Ui.Theme.selected : Ui.Theme.subtle
                                    radius: 7
                                    border.color: activityButton.visualFocus ? Ui.Theme.accent : "transparent"
                                }
                                contentItem: ColumnLayout {
                                    Text {
                                        text: activityButton.modelData.name
                                        color: Ui.Theme.muted
                                        font.pixelSize: 11
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: activityButton.modelData.display
                                        color: Ui.Theme.text
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
            Ui.StockMonthly {
                id: monthlySection
                visible: page.state.loaded
                Layout.fillWidth: true
                monthly: inventory.monthly
                controlsEnabled: page.controlsEnabled && page.state.current && !page.state.busy
                onMonthSelected: period => inventory.setMonthlyPeriod(period)
                onUnitSelected: unit => inventory.setMonthlyUnit(unit)
                onProductSelected: code => inventory.setFilter("product", code)
            }
            ColumnLayout {
                id: positionsSection
                visible: page.state.loaded
                Layout.fillWidth: true
                spacing: 10
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: "Posições de estoque"
                        color: Ui.Theme.text
                        font.pixelSize: 17
                        font.weight: Font.DemiBold
                    }
                    Ui.ActionButton {
                        text: "Detalhar produto"
                        enabled: page.state.selectedRow >= 0 && page.state.current && page.state.task !== "load"
                        iconName: "chart"
                        onClicked: stockDetail.open()
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(390, Math.max(180, page.height - 180))
                    color: Ui.Theme.line
                    clip: true
                    HorizontalHeaderView {
                        id: stockHeader
                        enabled: page.state.current && page.state.task !== "load"
                        anchors {
                            top: parent.top
                            left: parent.left
                            right: parent.right
                        }
                        height: 40
                        syncView: stockTable
                        clip: true
                        delegate: Rectangle {
                            required property int column
                            required property string display
                            implicitWidth: stockTable.columnWidthProvider(column)
                            implicitHeight: 40
                            color: Ui.Theme.subtle
                            Text {
                                anchors.fill: parent
                                anchors.margins: 10
                                text: display + (page.state.sortColumn === column ? page.state.descending ? " ↓" : " ↑" : "")
                                textFormat: Text.PlainText
                                color: Ui.Theme.text
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                            }
                            TapHandler {
                                onTapped: inventory.sortByColumn(column)
                            }
                            Accessible.role: Accessible.ColumnHeader
                            Accessible.name: "Ordenar por " + display
                            Accessible.onPressAction: inventory.sortByColumn(column)
                        }
                    }
                    TableView {
                        id: stockTable
                        enabled: page.state.current && page.state.task !== "load"
                        objectName: "stockTable"
                        anchors {
                            top: stockHeader.bottom
                            bottom: parent.bottom
                            left: parent.left
                            right: parent.right
                        }
                        model: stockModel
                        clip: true
                        activeFocusOnTab: true
                        Accessible.name: "Posições de estoque. Selecione com as setas e pressione Enter para detalhar."
                        Keys.onPressed: event => {
                            if (event.key === Qt.Key_Down) {
                                const row = Math.min(stockModel.rowCount() - 1, page.state.selectedRow + 1);
                                inventory.selectRow(row);
                                positionViewAtRow(row, TableView.Contain);
                            } else if (event.key === Qt.Key_Up) {
                                const row = Math.max(0, page.state.selectedRow - 1);
                                inventory.selectRow(row);
                                positionViewAtRow(row, TableView.Contain);
                            } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && page.state.selectedRow >= 0)
                                stockDetail.open();
                            else
                                event.accepted = false;
                        }
                        reuseItems: true
                        property bool compactMode: preferences.state.compact
                        onCompactModeChanged: forceLayout()
                        rowSpacing: 1
                        columnSpacing: 1
                        boundsBehavior: Flickable.StopAtBounds
                        columnWidthProvider: col => [120, 320, 80, 75, 65, 155, 180, 65, 120, 130, 130][col] || 120
                        rowHeightProvider: row => compactMode ? 32 : 40
                        ScrollBar.horizontal: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }
                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }
                        delegate: Rectangle {
                            required property int row
                            required property int column
                            required property string display
                            objectName: "stockCell_" + row + "_" + column
                            implicitWidth: stockTable.columnWidthProvider(column)
                            implicitHeight: preferences.state.compact ? 32 : 40
                            color: page.state.selectedRow === row ? Ui.Theme.selected : row % 2 ? Ui.Theme.subtle : Ui.Theme.surface
                            Text {
                                id: stockCell
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                text: display
                                textFormat: Text.PlainText
                                color: Ui.Theme.text
                                font.pixelSize: 12
                                verticalAlignment: Text.AlignVCenter
                                horizontalAlignment: column >= 5 && column !== 7 && column !== 8 ? Text.AlignRight : Text.AlignLeft
                                elide: Text.ElideRight
                            }
                            TapHandler {
                                onTapped: {
                                    inventory.selectRow(row);
                                    stockTable.forceActiveFocus();
                                }
                                onDoubleTapped: {
                                    inventory.selectRow(row);
                                    stockDetail.open();
                                }
                            }
                            HoverHandler {
                                id: cellHover
                            }
                            ToolTip.visible: cellHover.hovered && stockCell.truncated
                            ToolTip.text: display
                            ToolTip.delay: 400
                        }
                    }
                    Text {
                        anchors.centerIn: parent
                        visible: page.state.count === 0
                        text: "Nenhuma posição encontrada. Ajuste os filtros."
                        color: Ui.Theme.muted
                        font.pixelSize: 12
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: page.state.count + " posições"
                        color: Ui.Theme.muted
                        font.pixelSize: 12
                    }
                    Ui.ActionButton {
                        text: ""
                        iconName: "left"
                        implicitWidth: 40
                        enabled: page.state.page > 1
                        Accessible.name: "Página anterior"
                        onClicked: inventory.setPage(page.state.page - 1)
                    }
                    Text {
                        text: page.state.page + " / " + page.state.pages
                        color: Ui.Theme.text
                        font.pixelSize: 12
                    }
                    Ui.ActionButton {
                        text: ""
                        iconName: "right"
                        implicitWidth: 40
                        enabled: page.state.page < page.state.pages
                        Accessible.name: "Próxima página"
                        onClicked: inventory.setPage(page.state.page + 1)
                    }
                }
            }
        }
    }
    FileDialog {
        id: sourceDialog
        objectName: "stockSourceDialog"
        title: "Abrir base de estoque"
        currentFolder: stockDefaultFolder
        nameFilters: ["Base de estoque (*.liarte *.pbix)"]
        onAccepted: inventory.openFile(selectedFile)
    }
    FileDialog {
        id: saveStockDialog
        objectName: "stockSaveDialog"
        title: "Salvar estoque em Excel"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "xlsx"
        selectedFile: "Estoque_" + page.state.asOf.split("/").reverse().join("-") + ".xlsx"
        nameFilters: ["Excel (*.xlsx)"]
        onAccepted: inventory.exportExcel(selectedFile)
    }
    Ui.AppDialog {
        id: stockBackups
        objectName: "stockBackupsDialog"
        property var selected: null
        readonly property bool selectionAvailable: selected !== null && page.backupState.items.some(item => item.id === selected.id)
        title: "Restaurar base anterior"
        onOpened: {
            selected = null;
            inventory.refreshBackups();
        }
        onClosed: Qt.callLater(page.restoreFocus)
        Text {
            Layout.fillWidth: true
            text: "Escolha uma base salva antes de uma atualização. Até dez bases anteriores ficam disponíveis neste computador."
            textFormat: Text.PlainText
            color: Ui.Theme.muted
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        Text {
            objectName: "stockBackupsStatus"
            Layout.fillWidth: true
            visible: page.backupState.busy || page.backupState.error.length > 0 || page.backupState.notice.length > 0 || page.backupState.items.length === 0
            text: page.backupState.busy ? page.state.busyLabel : page.backupState.error || page.backupState.notice || "Nenhuma base anterior disponível. A base atual será preservada antes de uma próxima atualização."
            textFormat: Text.PlainText
            color: page.backupState.error.length ? Ui.Theme.danger : Ui.Theme.muted
            font.pixelSize: 12
            wrapMode: Text.WordWrap
            Accessible.role: Accessible.StaticText
        }
        ProgressBar {
            objectName: "stockBackupsProgress"
            Layout.fillWidth: true
            visible: page.backupState.busy
            indeterminate: true
        }
        Ui.ActionButton {
            id: cancelStockBackupTaskButton
            objectName: "cancelStockBackupTask"
            visible: page.backupState.busy
            text: "Cancelar operação"
            subtle: true
            onClicked: inventory.cancel()
        }
        Repeater {
            model: page.backupState.items
            delegate: Button {
                id: backupChoice
                required property var modelData
                required property int index
                objectName: "stockBackupChoice" + index
                Layout.fillWidth: true
                implicitHeight: backupChoiceContent.implicitHeight + 24
                padding: 12
                enabled: page.backupState.canRestore
                checked: stockBackups.selected !== null && stockBackups.selected.id === modelData.id
                Accessible.name: "Base de " + modelData.asOf + ". " + modelData.source + ". Salva em " + modelData.savedAt
                onClicked: stockBackups.selected = modelData
                contentItem: ColumnLayout {
                    id: backupChoiceContent
                    spacing: 4
                    Text {
                        Layout.fillWidth: true
                        text: "Base de " + backupChoice.modelData.asOf
                        textFormat: Text.PlainText
                        color: Ui.Theme.text
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        Layout.fillWidth: true
                        text: backupChoice.modelData.source
                        textFormat: Text.PlainText
                        color: Ui.Theme.text
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Salva em " + backupChoice.modelData.savedAt + " · " + backupChoice.modelData.products + " produtos"
                        textFormat: Text.PlainText
                        color: Ui.Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                }
                background: Rectangle {
                    radius: 7
                    color: backupChoice.checked ? Ui.Theme.selected : backupChoice.hovered ? Ui.Theme.subtle : Ui.Theme.surface
                    border.color: backupChoice.visualFocus || backupChoice.checked ? Ui.Theme.accent : Ui.Theme.line
                    border.width: backupChoice.visualFocus ? 2 : 1
                }
            }
        }
        Ui.ActionButton {
            id: reviewStockRestoreButton
            objectName: "reviewStockRestore"
            Layout.fillWidth: true
            text: "Restaurar base selecionada"
            primary: true
            enabled: stockBackups.selectionAvailable && page.backupState.canRestore
            onClicked: {
                confirmStockRestore.selected = stockBackups.selected;
                confirmStockRestore.open();
            }
        }
    }
    Ui.AppDialog {
        id: confirmStockRestore
        objectName: "confirmStockRestoreDialog"
        property var selected: null
        title: "Confirmar restauração"
        closeButton: false
        onOpened: Qt.callLater(() => cancelStockRestoreButton.forceActiveFocus(Qt.TabFocusReason))
        onClosed: if (stockBackups.visible)
            Qt.callLater(() => page.backupState.busy ? cancelStockBackupTaskButton.forceActiveFocus(Qt.TabFocusReason) : reviewStockRestoreButton.forceActiveFocus(Qt.TabFocusReason))
        Text {
            Layout.fillWidth: true
            text: "Restaurar a base de " + (confirmStockRestore.selected ? confirmStockRestore.selected.asOf : "") + "?"
            textFormat: Text.PlainText
            color: Ui.Theme.text
            font.pixelSize: 14
            font.weight: Font.DemiBold
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            text: confirmStockRestore.selected ? confirmStockRestore.selected.source : ""
            textFormat: Text.PlainText
            color: Ui.Theme.muted
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            text: "A base atual" + (page.state.asOf ? ", de " + page.state.asOf + "," : "") + " será substituída. Uma cópia dela será preservada quando válida. Seus relatórios e preferências serão mantidos."
            textFormat: Text.PlainText
            color: Ui.Theme.text
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        Ui.ActionButton {
            objectName: "confirmStockRestore"
            Layout.fillWidth: true
            text: "Restaurar esta base"
            primary: true
            enabled: confirmStockRestore.selected !== null && stockBackups.selectionAvailable && page.backupState.canRestore
            onClicked: {
                const selectedId = confirmStockRestore.selected.id;
                confirmStockRestore.close();
                inventory.restoreBackup(selectedId);
            }
        }
        Ui.ActionButton {
            id: cancelStockRestoreButton
            objectName: "cancelStockRestore"
            Layout.fillWidth: true
            text: "Cancelar"
            onClicked: confirmStockRestore.close()
        }
    }
    Ui.ChartDialog {
        id: stockChartDialog
        objectName: "stockChartDialog"
        title: "Evolução do estoque a custo"
        stock: true
        unit: "R$"
        contextLabel: (page.view.historySummary.period || "") + " · " + page.view.historicalScope
        legendLabel: "Custo mensal" + (stockTrend.hasAverage ? " · média de 3 meses (tracejada)" : "")
        points: page.view.plotTrend || []
        mode: stockTrend.mode
        movingAverage: stockTrend.movingAverage
        showValues: stockTrend.showValues
    }
    Ui.AppDialog {
        id: stockDetail
        readonly property string measure: detailMeasure.currentValue || "sales"
        readonly property var series: measure === "giro" ? page.detail.giroTrend : measure === "quantity" ? page.detail.stockQuantityTrend : measure === "cost" ? page.detail.stockCostTrend : page.detail.salesTrend
        readonly property string seriesTitle: measure === "giro" ? "Giro da fonte · posição" : measure === "quantity" ? "Quantidade no fechamento · posição" : measure === "cost" ? "Custo no fechamento · posição" : "Vendas da filial"
        readonly property string seriesUnit: measure === "giro" ? "x/mês" : measure === "cost" ? "R$" : page.detail.unit || ""
        objectName: "stockDetail"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(620, page.hostWindow.width - 36)
        height: Math.min(680, page.hostWindow.height - 36)
        modal: true
        title: "Detalhe do produto"
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 16
            Text {
                Layout.fillWidth: true
                text: page.detail.title || ""
                color: Ui.Theme.text
                font.pixelSize: 17
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }
            Text {
                text: page.detail.location || ""
                color: Ui.Theme.muted
                font.pixelSize: 12
                textFormat: Text.PlainText
            }
            Ui.ActionButton {
                text: "Analisar este produto"
                iconName: "filter"
                onClicked: {
                    inventory.setFilter("product", page.detail.code);
                    stockDetail.close();
                }
            }
            Ui.AppCombo {
                id: detailMeasure
                objectName: "stockDetailMeasure"
                Layout.fillWidth: true
                model: [
                    {
                        value: "sales",
                        label: "Vendas da filial"
                    },
                    {
                        value: "giro",
                        label: "Giro da fonte"
                    },
                    {
                        value: "quantity",
                        label: "Quantidade no fechamento"
                    },
                    {
                        value: "cost",
                        label: "Custo no fechamento"
                    }
                ]
                Accessible.name: "Indicador mensal do produto"
            }
            Text {
                Layout.fillWidth: true
                text: stockDetail.seriesTitle + " · " + stockDetail.seriesUnit
                textFormat: Text.PlainText
                color: Ui.Theme.muted
                font.pixelSize: 11
            }
            ColumnLayout {
                id: detailChartGroup
                Layout.fillWidth: true
                spacing: 12
                Ui.StockPlot {
                    id: detailTrend
                    objectName: "stockDetailTrend"
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(110, Math.min(200, stockDetail.bodyViewportHeight - detailTrendReadout.implicitHeight - detailChartGroup.spacing))
                    points: stockDetail.series || []
                    unit: stockDetail.seriesUnit
                    precision: 2
                    mode: stockDetail.measure === "sales" ? "column" : "line"
                    movingAverage: false
                    seriesName: stockDetail.seriesTitle
                    onActiveFocusChanged: if (activeFocus)
                        Qt.callLater(() => stockDetail.reveal(detailChartGroup))
                    onReadoutChanged: if (activeFocus)
                        Qt.callLater(() => stockDetail.reveal(detailChartGroup))
                }
                Text {
                    id: detailTrendReadout
                    objectName: "stockDetailTrendReadout"
                    Layout.fillWidth: true
                    text: detailTrend.readout || "Selecione um mês com o cursor ou as setas. Vendas pertencem à filial; fechamentos e giro pertencem à posição."
                    textFormat: Text.PlainText
                    color: Ui.Theme.muted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
            }
            Repeater {
                model: [["Saldo atual", "balance"], ["Custo atual", "cost"], ["Última venda", "lastSale"], ["Vendas no período", "sold"], ["Cobertura por vendas · filial", "coverage"], ["Média mensal de vendas", "mean"], ["Desvio padrão mensal", "std"], ["Variação da demanda · CV", "cv"], ["Giro mensal · fonte", "turnover"], ["Fechamento do giro", "sourcePeriod"]]
                RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: modelData[0]
                        color: Ui.Theme.muted
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        Layout.maximumWidth: page.hostWindow.width < 650 ? 155 : 270
                        text: page.detail[modelData[1]] || "—"
                        color: Ui.Theme.text
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                        textFormat: Text.PlainText
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                text: "Estatística: " + (page.detail.months || 0) + " meses completos, incluindo meses sem venda. Cobertura usa todas as posições da filial e não representa consumo interno."
                color: Ui.Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
        }
    }

    Ui.AppDialog {
        id: stockMethodology
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(590, page.hostWindow.width - 36)
        height: Math.min(620, page.hostWindow.height - 36)
        modal: true
        title: "Leitura dos indicadores"
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth
            Text {
                width: parent.width
                text: (page.state.notes.length ? page.state.notes.join("\n") + "\n\n" : "") + "Os saldos são os atuais na data da base; o período filtra vendas e fechamentos históricos.\n\nCapital: custo do saldo selecionado, em reais. Quantidades de unidades diferentes não são somadas.\n\nGiro: valor mensal em quantidade informado no BI, no último fechamento. O cartão mostra a mediana dos giros não negativos de posições com saldo positivo; não é giro consolidado. Valores de giro e dias da fonte não são recalculados.\n\nCobertura: saldo de todas as posições de uma filial / média diária das vendas no período. Sem cálculo com filtro de armazém, saldo negativo ou sem vendas positivas; não mede consumo interno.\n\nCV: desvio padrão amostral / média de vendas mensais, com pelo menos três meses completos. Inclui meses sem documentos de venda; meses incompletos são excluídos.\n\nABC: capital positivo por produto; A até atingir 80%, B até 95%, C restante. O produto que cruza o limite permanece na classe anterior. O filtro ABC não recalcula as classes.\n\nÚltima venda: última saída positiva do produto na filial e unidade, até a data da base. Produtos sem venda não são classificados automaticamente como obsoletos.\n\nO histórico pode cobrir menos locais que o saldo atual. Meses sem fechamento permanecem sem valor. O PBIX é lido localmente, sem atualizar ou alterar o BI da empresa."
                textFormat: Text.PlainText
                color: Ui.Theme.text
                wrapMode: Text.WordWrap
                font.pixelSize: 13
                lineHeight: 1.2
            }
        }
    }
}
