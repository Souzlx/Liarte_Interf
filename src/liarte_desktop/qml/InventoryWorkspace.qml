import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "components" as Ui

FocusScope {
    id: page
    objectName: "inventoryWorkspace"
    required property var hostWindow
    readonly property var state: inventory.presentation
    readonly property var view: inventory.analysis
    readonly property var detail: inventory.detail
    readonly property var backupState: inventory.backupState
    readonly property bool modalOpen: sourceDialog.visible || stockFilters.visible || saveStockDialog.visible || stockDetail.visible || stockPerformance.visible || stockMethodology.visible || stockChartDialog.visible || stockBackups.visible || confirmStockRestore.visible || stockAlerts.modalOpen || monthlySection.modalOpen
    readonly property bool controlsEnabled: state.loaded && state.task !== "load" && state.task !== "export"
    property string activeSection: "overview"
    property var sectionScroll: ({
            overview: 0,
            monthly: 0,
            products: 0
        })
    property int navigationRevision: 0
    property bool navigating: false
    property bool showAlerts: false
    property var pendingOverviewTarget: null
    readonly property var appliedSelection: state.appliedSelection || state.selection || ({})
    readonly property var branchOption: inventory.filterOptions.find(option => option.key === "branch") || ({
            values: []
        })
    readonly property int advancedFilterCount: ["warehouse", "group", "kind", "abc", "activity", "balance"].filter(key => Boolean(appliedSelection[key])).length
    readonly property string advancedFilterSummary: {
        const labels = {warehouse: "Armazém", group: "Grupo", kind: "Tipo", abc: "ABC", activity: "Última venda", balance: "Saldo"};
        const balances = {positive: "positivo", zero: "zerado", negative: "negativo"};
        return Object.keys(labels).filter(key => Boolean(appliedSelection[key])).map(key => labels[key] + ": " + (key === "balance" ? balances[appliedSelection[key]] || appliedSelection[key] : appliedSelection[key])).join(" · ");
    }
    property var lastFocusedControl: null
    property var pendingAlertTarget: null
    property var pendingComparisonFocus: null

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
    function firstFocusableControl(parentItem) {
        for (const item of parentItem.children) {
            if (!item.visible || !item.enabled)
                continue;
            if (item.activeFocusOnTab)
                return item;
            const child = firstFocusableControl(item);
            if (child)
                return child;
        }
        return null;
    }
    function navigate(section) {
        if (!["overview", "monthly", "products"].includes(section))
            return;
        if (section === activeSection) {
            restoreFocus();
            return;
        }
        if (!navigating)
            sectionScroll[activeSection] = scroll.contentY;
        const destination = sectionScroll[section] || 0;
        const revision = ++navigationRevision;
        navigating = true;
        stockScrollMotion.stop();
        scroll.cancelFlick();
        activeSection = section;
        Qt.callLater(() => {
            if (revision !== navigationRevision)
                return;
            scroll.contentY = Math.max(0, Math.min(destination, scroll.contentHeight - scroll.height));
            Qt.callLater(() => {
                if (revision !== navigationRevision)
                    return;
                navigating = false;
                const owner = activeSection === "products" ? positionsSection : activeSection === "monthly" ? monthlySection : overviewSection;
                const target = destination > 0 ? firstVisibleControl(content) : firstFocusableControl(owner);
                if (target && page.visible) {
                    target.forceActiveFocus(Qt.TabFocusReason);
                    revealComparisonFocus(target);
                } else
                    restoreFocus();
            });
        });
    }
    function appliedPeriod() {
        const start = appliedSelection.start || "";
        const end = appliedSelection.end || "";
        return start && end ? start.slice(5) + "/" + start.slice(0, 4) + " a " + end.slice(5) + "/" + end.slice(0, 4) : "Sem período disponível";
    }
    function finishOverviewNavigation() {
        if (!pendingOverviewTarget)
            return;
        if (!visible || state.error.length > 0) {
            pendingOverviewTarget = null;
            return;
        }
        if (!state.current || state.busy)
            return;
        const target = pendingOverviewTarget;
        pendingOverviewTarget = null;
        if (state.selection[target.dimension] === target.key)
            navigate("products");
    }
    function restoreFocus() {
        const item = visibleControl(lastFocusedControl) ? lastFocusedControl : firstVisibleControl(content);
        if (item)
            item.forceActiveFocus(Qt.TabFocusReason);
        else
            page.forceActiveFocus();
    }
    function revealComparisonFocus(item) {
        if (!item || !item.activeFocus || !page.visible || page.modalOpen)
            return;
        let belongs = false;
        for (let ancestor = item; ancestor; ancestor = ancestor.parent) {
            if (ancestor === content) {
                belongs = true;
                break;
            }
        }
        if (!belongs)
            return;
        const top = item.mapToItem(scroll, 0, 0).y;
        const maximum = Math.max(0, scroll.contentHeight - scroll.height);
        if (top < 0 || top + item.height > scroll.height) {
            stockScrollMotion.stop();
            scroll.cancelFlick();
            scroll.contentY = Math.max(0, Math.min(maximum, scroll.contentY + (top < 0 ? top - 8 : top + item.height - scroll.height + 8)));
        }
    }
    function scheduleComparisonFocusReveal() {
        Qt.callLater(() => {
            if (page.hostWindow)
                page.revealComparisonFocus(page.hostWindow.activeFocusItem);
        });
    }
    function finishAlertNavigation() {
        if (!pendingAlertTarget)
            return;
        if (!visible || state.error.length > 0) {
            pendingAlertTarget = null;
            return;
        }
        if (!state.current || state.busy)
            return;
        const target = pendingAlertTarget;
        pendingAlertTarget = null;
        if (state.selection.product === target.code && state.selection.branch === target.branch && state.selection.unit === target.unit)
            navigate("products");
    }
    Connections {
        target: inventory
        function onChanged() {
            if (page.pendingOverviewTarget)
                Qt.callLater(page.finishOverviewNavigation);
            if (page.pendingAlertTarget)
                Qt.callLater(page.finishAlertNavigation);
            if (page.pendingComparisonFocus)
                Qt.callLater(page.finishComparisonNavigation);
        }
    }
    function finishComparisonNavigation() {
        if (!pendingComparisonFocus)
            return;
        if (state.error.length && !state.busy) {
            pendingComparisonFocus = null;
            return;
        }
        if (!state.current || state.busy)
            return;
        const target = pendingComparisonFocus;
        pendingComparisonFocus = null;
        if (state.selection[target.dimension] === target.key)
            navigate("monthly");
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
                    Qt.callLater(() => page.revealComparisonFocus(item));
                    return;
                }
            }
        }
    }
    Shortcut {
        sequence: "Ctrl+F"
        enabled: page.visible && page.state.loaded && !page.modalOpen && !hostWindow.globalModalOpen
        onActivated: {
            page.navigationRevision++;
            page.navigating = false;
            stockScrollMotion.stop();
            scroll.cancelFlick();
            scroll.contentY = 0;
            stockSearch.focusSearch();
            Qt.callLater(() => page.revealComparisonFocus(stockSearch));
        }
    }
    NumberAnimation {
        id: stockScrollMotion
        target: scroll
        property: "contentY"
        duration: Ui.Theme.motion
        easing.type: Easing.OutCubic
    }
    onVisibleChanged: if (!visible) {
        navigationRevision++;
        navigating = false;
        stockScrollMotion.stop();
        pendingAlertTarget = null;
        pendingComparisonFocus = null;
        pendingOverviewTarget = null;
    }
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
        onWidthChanged: page.scheduleComparisonFocusReveal()
        onHeightChanged: page.scheduleComparisonFocusReveal()
        onContentHeightChanged: page.scheduleComparisonFocusReveal()
        onContentYChanged: if (!page.navigating)
            page.sectionScroll[page.activeSection] = contentY
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
                id: stockPageHeader
                Layout.fillWidth: true
                columns: page.width < 720 || width < stockHeaderActions.fourActionWidth + 220 ? 1 : 2
                rowSpacing: 12
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Text {
                        Layout.fillWidth: true
                        text: page.state.loaded ? page.activeSection === "monthly" ? "Estoque · mês a mês" : page.activeSection === "products" ? "Estoque · produtos" : "Panorama do estoque" : "Estoque e rotatividade"
                        textFormat: Text.PlainText
                        color: Ui.Theme.text
                        font.pixelSize: page.width < 600 ? 21 : 25
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        Layout.fillWidth: true
                        text: page.state.loaded ? "Base em " + page.state.asOf + " · " + (page.activeSection === "monthly" ? "Fechamentos e vendas no período selecionado" : page.activeSection === "products" ? "Saldos atuais e desempenho por produto" : "Saldos atuais e evolução dos fechamentos") : platform.development ? "Abra uma base de teste neste perfil separado." : "Preparando a base de estoque da LIARTE."
                        textFormat: Text.PlainText
                        color: Ui.Theme.muted
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                }
                GridLayout {
                    id: stockHeaderActions
                    objectName: "stockHeaderActions"
                    readonly property real fourActionWidth: 4 * Math.ceil(Math.max(openBase.naturalWidth, exportStock.visible ? exportStock.naturalWidth : 0, restoreStock.implicitWidth, stockMethodologyAction.implicitWidth)) + 3 * columnSpacing
                    Layout.alignment: Qt.AlignRight
                    Layout.fillWidth: stockPageHeader.columns === 1
                    Layout.minimumWidth: 0
                    columns: content.width >= fourActionWidth ? 4 : 2
                    columnSpacing: 8
                    rowSpacing: 8
                    Ui.ActionButton {
                        id: openBase
                        objectName: "openStockBase"
                        text: page.width < 720 ? "Base" : page.state.loaded ? "Atualizar base" : "Abrir base"
                        Accessible.name: page.state.loaded ? "Atualizar base de estoque" : "Abrir base de estoque"
                        iconName: "folder"
                        primary: !page.state.loaded
                        Layout.fillWidth: stockHeaderActions.columns === 2
                        Layout.minimumWidth: 0
                        enabled: !page.state.busy
                        onClicked: sourceDialog.open()
                    }
                    Ui.ActionButton {
                        id: exportStock
                        objectName: "stockExportButton"
                        visible: page.state.loaded
                        text: page.width < 720 ? "Excel" : "Baixar Excel"
                        Accessible.name: "Baixar Excel do estoque"
                        iconName: "download"
                        Layout.fillWidth: stockHeaderActions.columns === 2
                        Layout.minimumWidth: 0
                        enabled: !page.state.busy && page.state.current && inventory.comparisonState.current && !inventory.performance.state.busy
                        onClicked: saveStockDialog.open()
                    }
                    Ui.ActionButton {
                        id: restoreStock
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
                        id: stockMethodologyAction
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
                        objectName: "stockEmptyExplanation"
                        text: platform.development ? "Este perfil começa vazio. Abra uma base de teste; seus dados de uso ficam preservados." : "A base integrada abre automaticamente. Para atualizar os dados, utilize um novo arquivo da empresa."
                        textFormat: Text.PlainText
                        color: Ui.Theme.muted
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                    }
                }
            }
            RowLayout {
                objectName: "stockSectionNavigation"
                visible: page.state.loaded && page.width < 900
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 8
                Repeater {
                    model: [
                        {
                            key: "overview",
                            label: "Panorama"
                        },
                        {
                            key: "monthly",
                            label: "Mês a mês"
                        },
                        {
                            key: "products",
                            label: "Produtos"
                        }
                    ]
                    Ui.ActionButton {
                        required property var modelData
                        objectName: "stockSection_" + modelData.key
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: modelData.label
                        primary: page.activeSection === modelData.key
                        subtle: page.activeSection !== modelData.key
                        Accessible.name: "Abrir " + modelData.label + " do estoque"
                        onClicked: page.navigate(modelData.key)
                    }
                }
            }
            Rectangle {
                objectName: "stockFilterBar"
                visible: page.state.loaded
                Layout.fillWidth: true
                implicitHeight: filterContent.implicitHeight + 28
                radius: Ui.Theme.radius
                color: Ui.Theme.surface
                border.color: Ui.Theme.softLine
                ColumnLayout {
                    id: filterContent
                    x: 14
                    y: 14
                    width: parent.width - 28
                    spacing: 10
                    enabled: page.controlsEnabled
                    GridLayout {
                        id: quickStockGrid
                        readonly property real cellWidth: Math.max(0, (width - (columns - 1) * columnSpacing) / columns)
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        columns: width >= 700 ? 4 : 2
                        columnSpacing: 10
                        rowSpacing: 10
                        ColumnLayout {
                            Layout.columnSpan: 2
                            Layout.preferredWidth: 2 * quickStockGrid.cellWidth + quickStockGrid.columnSpacing
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            spacing: 5
                            Text {
                                Layout.fillWidth: true
                                text: "Produto"
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                            Ui.StockSearch {
                                id: stockSearch
                                objectName: "stockProductSearch"
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                            }
                        }
                        ColumnLayout {
                            Layout.preferredWidth: quickStockGrid.cellWidth
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            spacing: 5
                            Text {
                                Layout.fillWidth: true
                                text: "Filial"
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                            Ui.AppCombo {
                                objectName: "stockFilter_branch"
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                model: page.branchOption.values
                                currentIndex: Math.max(0, model.findIndex(option => option.value === (page.state.selection.branch || "")))
                                Accessible.name: "Filial do estoque"
                                onActivated: inventory.setFilter("branch", currentValue)
                            }
                        }
                        Ui.ActionButton {
                            objectName: "stockRefineFilters"
                            Layout.preferredWidth: quickStockGrid.cellWidth
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            Layout.alignment: Qt.AlignBottom
                            text: "Refinar recorte" + (page.advancedFilterCount ? " (" + page.advancedFilterCount + ")" : "")
                            iconName: "filter"
                            Accessible.name: "Refinar filtros e período do estoque"
                            onClicked: stockFilters.open()
                        }
                    }
                    Text {
                        objectName: "stockAppliedScope"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: (page.state.current ? "Histórico: " : "Último recorte concluído: ") + page.appliedPeriod() + " · " + (page.appliedSelection.unit || "Quantidades separadas por unidade") + (page.advancedFilterCount ? " · " + page.advancedFilterCount + " filtros adicionais" : "")
                        textFormat: Text.PlainText
                        color: Ui.Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        Accessible.description: page.advancedFilterSummary
                        ToolTip.visible: scopeHover.hovered && Boolean(page.advancedFilterSummary)
                        ToolTip.text: page.advancedFilterSummary
                        ToolTip.delay: 350
                        HoverHandler {
                            id: scopeHover
                        }
                    }
                }
            }
            Ui.StockOverview {
                id: overviewSection
                visible: page.state.loaded && page.activeSection === "overview"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                view: page.view
                current: page.state.current
                controlsEnabled: page.controlsEnabled && !page.state.busy
                onChartRequested: stockChartDialog.open()
                onProductSelected: code => {
                    page.pendingOverviewTarget = {
                        dimension: "product",
                        key: code
                    };
                    inventory.setFilter("product", code);
                    Qt.callLater(page.finishOverviewNavigation);
                }
                onActivitySelected: activity => {
                    page.pendingOverviewTarget = {
                        dimension: "activity",
                        key: activity
                    };
                    inventory.setFilter("activity", activity);
                    Qt.callLater(page.finishOverviewNavigation);
                }
            }
            Ui.ActionButton {
                objectName: "stockAlertsToggle"
                visible: page.state.loaded && page.activeSection === "overview"
                Layout.fillWidth: page.width < 600
                Layout.minimumWidth: 0
                text: page.showAlerts ? "Recolher alertas do estoque" : "Ver alertas do estoque"
                iconName: "info"
                onClicked: page.showAlerts = !page.showAlerts
            }
            Ui.StockAlerts {
                id: stockAlerts
                visible: page.state.loaded && page.activeSection === "overview" && page.showAlerts
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                alertData: inventory.alerts
                settings: inventory.alertSettings
                current: page.state.current
                busy: page.state.busy
                controlsEnabled: page.controlsEnabled
                onThresholdsApplied: (staleDays, coverageDays) => inventory.setAlertThresholds(staleDays, coverageDays)
                onProductRequested: (code, branch, unit) => {
                    page.pendingAlertTarget = {
                        code: code,
                        branch: branch,
                        unit: unit
                    };
                    inventory.focusAlertProduct(code, branch, unit);
                    Qt.callLater(page.finishAlertNavigation);
                }
            }
            Ui.StockMonthly {
                id: monthlySection
                visible: page.state.loaded && page.activeSection === "monthly"
                Layout.fillWidth: true
                monthly: inventory.monthly
                comparison: inventory.comparison
                comparisonState: inventory.comparisonState
                comparisonEnabled: page.controlsEnabled && page.state.current && (!page.state.busy || page.state.task === "comparison")
                controlsEnabled: page.controlsEnabled && page.state.current && !page.state.busy
                onComparisonRequested: (base, target) => inventory.setComparisonMonths(base, target)
                onComparisonFocusRequested: (dimension, key) => {
                    page.pendingComparisonFocus = {
                        dimension: dimension,
                        key: key
                    };
                    inventory.focusComparison(dimension, key);
                    Qt.callLater(page.finishComparisonNavigation);
                }
                onMonthSelected: period => inventory.setMonthlyPeriod(period)
                onUnitSelected: unit => inventory.setMonthlyUnit(unit)
                onProductSelected: code => inventory.setFilter("product", code)
            }
            Ui.StockPositions {
                id: positionsSection
                visible: page.state.loaded && page.activeSection === "products"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                state: page.state
                tableModel: stockModel
                controlsEnabled: page.controlsEnabled
                compact: preferences.state.compact
                viewportHeight: page.height
                onPerformanceRequested: stockPerformance.open()
                onDetailRequested: stockDetail.open()
                onSortRequested: column => inventory.sortByColumn(column)
                onRowSelected: row => inventory.selectRow(row)
                onPageSelected: requestedPage => inventory.setPage(requestedPage)
            }
        }
    }
    Ui.StockFiltersDialog {
        id: stockFilters
        stockController: inventory
        controlsEnabled: page.controlsEnabled
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
        legendLabel: "Custo mensal" + (overviewSection.chartHasAverage ? " · média de 3 meses (tracejada)" : "")
        points: page.view.plotTrend || []
        mode: overviewSection.chartMode
        movingAverage: overviewSection.chartMovingAverage
        showValues: overviewSection.chartShowValues
    }
    Ui.StockPerformance {
        id: stockPerformance
        performance: inventory.performance
        controlsEnabled: page.controlsEnabled && page.state.current && !page.state.busy
        onProductFocusRequested: (code, unit) => inventory.focusPerformanceProduct(code, unit)
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
