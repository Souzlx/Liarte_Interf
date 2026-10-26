import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "components" as Ui

FocusScope {
    id: window
    objectName: "importsWorkspace"
    required property var hostWindow
    required property Item exportAnchor
    property bool globalModalOpen: false
    function openExportMenu() {
        quickExportMenu.open();
    }
    property string activeSection: "summary"
    property string primaryVisual: "trend"
    property bool periodExpanded: false
    property bool documentsExpanded: false
    property var sectionPositions: ({
            summary: 0,
            buying: 0,
            records: 0
        })
    property var sectionFocus: ({})
    property string lastAppliedPeriod: ""

    function belongsToWorkspace(item) {
        for (let ancestor = item; ancestor; ancestor = ancestor.parent)
            if (ancestor === window)
                return true;
        return false;
    }
    function restoreFocus() {
        if (!viewState.loaded) {
            queryPanel.focusQuery();
            return;
        }
        const saved = sectionFocus[activeSection];
        if (saved && saved.visible && saved.enabled && belongsToWorkspace(saved)) {
            saved.forceActiveFocus(Qt.TabFocusReason);
            reveal(saved);
        } else if (activeSection === "records")
            recordsPanel.focusFirst();
        else if (activeSection === "buying")
            buyingSection.focusFirst();
        else if (primaryVisual === "trend")
            trendPanel.focusFirst();
        else
            visualOrigins.forceActiveFocus(Qt.TabFocusReason);
    }
    Connections {
        target: window.hostWindow
        function onActiveFocusItemChanged() {
            const item = window.hostWindow.activeFocusItem;
            if (window.visible && !window.modalOpen && item && window.belongsToWorkspace(item))
                window.sectionFocus[window.activeSection] = item;
        }
    }
    readonly property var viewState: controller.presentation
    readonly property var analysis: controller.analysis
    readonly property var buying: analysis.procurement
    property int originLimit: 8
    property bool filtersExpanded: false
    property bool methodologyExpanded: false
    readonly property bool localActivityPending: viewState.loaded && (viewState.waiting || (viewState.busy && viewState.localBusy))
    property bool localActivityVisible: false
    onLocalActivityPendingChanged: {
        if (localActivityPending)
            localActivityDelay.restart();
        else {
            localActivityDelay.stop();
            localActivityVisible = false;
        }
    }
    Timer {
        id: localActivityDelay
        interval: 180
        onTriggered: window.localActivityVisible = window.localActivityPending
    }
    function chooseProduct() {
        filterPanel.chooseProduct();
    }
    readonly property var matchingOrigins: {
        if (!buying.comparable)
            return [];
        const rows = buying.origins.filter(row => row.kgValue >= Number(buyingSection.minimumWeight || 0));
        const order = buyingSection.order || "volume";
        rows.sort((a, b) => {
            if (order === "volume")
                return a.volumeRank - b.volumeRank;
            if (a.price === null || b.price === null)
                return a.price === null ? (b.price === null ? a.volumeRank - b.volumeRank : 1) : -1;
            return order === "low" ? a.priceRank - b.priceRank : b.priceRank - a.priceRank;
        });
        return rows;
    }
    onBuyingChanged: originLimit = 8
    function navigate(section) {
        if (section === "documents") {
            documentsExpanded = true;
            navigate("records");
            Qt.callLater(() => reveal(documentsPanel));
            return;
        }
        if (!["summary", "buying", "records"].includes(section))
            return;
        if (activeSection !== section) {
            sectionPositions[activeSection] = contentScroll.contentY;
            activeSection = section;
            navigation.stop();
            if (Ui.Theme.motionEnabled)
                navigation.restart();
            else
                body.opacity = 1;
        }
        Qt.callLater(() => {
            const maximum = Math.max(0, contentScroll.contentHeight - contentScroll.height);
            contentScroll.contentY = Math.max(0, Math.min(maximum, sectionPositions[activeSection] || 0));
            Qt.callLater(window.restoreFocus);
        });
    }
    NumberAnimation {
        id: navigation
        objectName: "navigationAnimation"
        target: body
        property: "opacity"
        from: 0.96
        to: 1
        duration: 140
        easing.type: Easing.OutCubic
    }
    Connections {
        target: Ui.Theme
        function onMotionEnabledChanged() {
            if (!Ui.Theme.motionEnabled) {
                navigation.stop();
                body.opacity = 1;
            }
        }
    }
    readonly property string trendKey: trendPanel.trendKey
    readonly property var trendData: trendPanel.trendData
    readonly property bool modalOpen: globalModalOpen || detailDialog.visible || exportDialog.visible || filterPanel.modalOpen || queryPanel.modalOpen || trendPanel.modalOpen || buyingSection.modalOpen || recordsPanel.modalOpen || quickExportMenu.visible || trendValuesDialog.visible || importChartDialog.visible
    readonly property bool draftPeriod: viewState.loaded && (queryPanel.startValue !== viewState.appliedStart || queryPanel.endValue !== viewState.appliedEnd)
    readonly property bool collapsed: hostWindow.width < 1120
    readonly property var headers: viewState.headers
    readonly property string shownKind: viewState.appliedKind
    onShownKindChanged: {
        recordsPanel.resetPosition();
    }
    readonly property string valueBasis: viewState.appliedKind === "municipal" ? "FOB" : "CIF"
    readonly property int pauseSeconds: viewState.sourcePauseSeconds || 0
    readonly property string pauseLabel: Math.floor(pauseSeconds / 60) + ":" + String(pauseSeconds % 60).padStart(2, "0")
    function sourcePauseError(message) {
        return message.includes("Comex Stat solicitou uma pausa") || /HTTP\s*429|"code"\s*:\s*429/.test(message);
    }
    function userError(message) {
        if (message.includes("Comex Stat solicitou uma pausa"))
            return "A pausa solicitada pelo Comex Stat terminou. Você pode consultar novamente.";
        if (sourcePauseError(message))
            return "O Comex Stat está com limite de consultas. Você pode tentar novamente.";
        if (/HTTP\s*5\d\d/.test(message))
            return "O Comex Stat está temporariamente indisponível. Tente novamente em instantes.";
        if (/HTTP\s*(401|403)/.test(message))
            return "O Comex Stat não permitiu a consulta. Verifique o acesso à fonte e tente novamente.";
        if (/timed out|TimeoutError|tempo total.*excedido/i.test(message))
            return "O Comex Stat demorou a responder. Tente novamente; os dados anteriores foram mantidos.";
        return message.replace(/^(Consulta oficial não concluída:\s*)+/, "");
    }
    function saveDocument(kind) {
        exportDialog.exportKind = kind;
        const suffix = kind === "excel" ? "xlsx" : kind === "pdf" ? "pdf" : "zip";
        const stem = kind === "pdf" ? "IMPORTACOES_FILTRADAS" : kind === "powerbi" ? "POWERBI_LIARTE_IMPORTACOES" : "IMPORTACAO";
        exportDialog.nameFilters = [kind === "excel" ? "Excel (*.xlsx)" : kind === "pdf" ? "PDF (*.pdf)" : "Projeto Power BI (*.zip)"];
        exportDialog.defaultSuffix = suffix;
        exportDialog.selectedFile = controller.reportsFolder + "/" + stem + "_" + viewState.appliedStart + "_" + viewState.appliedEnd + "." + suffix;
        exportDialog.open();
    }
    function reveal(item) {
        if (!item || !item.visible)
            return;
        const point = item.mapToItem(contentScroll.contentItem, 0, 0);
        const maximum = Math.max(0, contentScroll.contentHeight - contentScroll.height);
        if (point.y < contentScroll.contentY)
            contentScroll.contentY = Math.max(0, point.y - 12);
        else if (point.y + item.height > contentScroll.contentY + contentScroll.height)
            contentScroll.contentY = Math.min(maximum, point.y + Math.min(item.height, contentScroll.height) - contentScroll.height + 12);
    }
    Connections {
        target: controller
        function onPresentationChanged() {
            if (window.viewState.selection < 0 && detailDialog.visible)
                detailDialog.close();
            const applied = window.viewState.appliedStart + "/" + window.viewState.appliedEnd;
            if (window.viewState.loaded && applied !== window.lastAppliedPeriod) {
                window.periodExpanded = false;
                window.lastAppliedPeriod = applied;
            }
        }
    }
    Shortcut {
        sequence: "Ctrl+F"
        enabled: window.visible && window.viewState.loaded && !window.modalOpen
        onActivated: {
            window.navigate("records");
            Qt.callLater(() => recordsPanel.focusSearch());
        }
    }
    Shortcut {
        sequence: "F5"
        enabled: window.visible && !window.viewState.busy && !window.viewState.metadataBusy && window.pauseSeconds === 0 && !window.modalOpen
        onActivated: controller.queryPeriod(queryPanel.startValue, queryPanel.endValue)
    }

    readonly property var activeFilters: [
        {
            key: "ncm",
            title: viewState.kind === "municipal" ? "SH4" : "Produto",
            values: viewState.ncmValues,
            options: viewState.ncmValues.length ? controller.products : []
        },
        {
            key: "country",
            title: "País",
            values: viewState.countryValues,
            options: viewState.countryValues.length ? controller.countries : []
        },
        {
            key: "state",
            title: "UF",
            values: viewState.stateValues,
            options: viewState.stateValues.length ? controller.states : []
        },
        {
            key: "port",
            title: "Porto",
            values: viewState.portValues,
            options: viewState.portValues.length ? controller.ports : []
        },
        {
            key: "city",
            title: "Município",
            values: viewState.cityValues,
            options: viewState.cityValues.length ? controller.cities : []
        }
    ].filter(group => group.values.length > 0).map(group => ({
                key: group.key,
                caption: group.title + ": " + (group.values.length > 1 ? group.values.length + " selecionados" : (group.options.find(option => option.value === group.values[0]) || {
                            label: group.values[0]
                        }).label),
                description: group.values.map(value => (group.options.find(option => option.value === value) || {
                            label: value
                        }).label).join("\n")
            }))

    Flickable {
        id: contentScroll
        objectName: "contentScroll"
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: body.implicitHeight + 48
        boundsBehavior: Flickable.StopAtBounds
        onMovementStarted: navigation.stop()
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }
        ColumnLayout {
            id: body
            x: window.hostWindow.width < 720 ? 18 : 28
            y: 18
            width: contentScroll.width - (window.hostWindow.width < 720 ? 36 : 56)
            spacing: 16
            Rectangle {
                visible: window.viewState.demo || window.viewState.sourceNotice.length > 0
                Layout.fillWidth: true
                Layout.preferredHeight: sourceNote.implicitHeight + 24
                radius: 7
                color: Ui.Theme.warningBg
                Text {
                    id: sourceNote
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    anchors.margins: 12
                    text: window.viewState.demo ? "DEMONSTRAÇÃO · Dados fictícios." : window.viewState.sourceNotice
                    color: Ui.Theme.warningText
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
            }
            Ui.ImportQueryPanel {
                id: queryPanel
                workspace: window
                backend: controller
            }
            Rectangle {
                objectName: "emptyState"
                visible: !window.viewState.loaded && !window.viewState.busy
                Layout.fillWidth: true
                Layout.preferredHeight: 246
                radius: Ui.Theme.radius
                color: Ui.Theme.surface
                border.color: Ui.Theme.line
                Column {
                    anchors.centerIn: parent
                    width: parent.width - 40
                    spacing: 14
                    Ui.Icon {
                        anchors.horizontalCenter: parent.horizontalCenter
                        name: "chart"
                        width: 32
                        height: 32
                        color: Ui.Theme.accent
                    }
                    Text {
                        textFormat: Text.PlainText
                        width: parent.width
                        text: "Comece pelo período"
                        color: Ui.Theme.text
                        font.pixelSize: 20
                        font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignHCenter
                    }
                    Text {
                        textFormat: Text.PlainText
                        width: parent.width
                        text: "Selecione os meses para consultar as importações."
                        color: Ui.Theme.muted
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }
                }
            }
            RowLayout {
                visible: !window.viewState.demo && window.viewState.loaded
                Layout.fillWidth: true
                spacing: 4
                Rectangle {
                    Layout.preferredWidth: Math.min(310, body.width)
                    Layout.preferredHeight: 40
                    color: Ui.Theme.subtle
                    radius: 8
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 3
                        spacing: 3
                        Ui.ActionButton {
                            objectName: "generalTab"
                            Layout.fillWidth: true
                            implicitHeight: 34
                            text: "Dados gerais"
                            primary: false
                            enabled: !window.viewState.busy || window.viewState.localBusy
                            onClicked: controller.setDataset("general")
                            background: Rectangle {
                                radius: 6
                                color: window.viewState.kind === "general" ? Ui.Theme.surface : "transparent"
                                Behavior on color {
                                    enabled: Ui.Theme.motionEnabled
                                    ColorAnimation {
                                        duration: 140
                                    }
                                }
                                border.color: parent.activeFocus ? Ui.Theme.accent : "transparent"
                            }
                        }
                        Ui.ActionButton {
                            objectName: "municipalTab"
                            Layout.fillWidth: true
                            implicitHeight: 34
                            text: "Municípios"
                            enabled: !window.viewState.busy || window.viewState.localBusy
                            onClicked: controller.setDataset("municipal")
                            background: Rectangle {
                                radius: 6
                                color: window.viewState.kind === "municipal" ? Ui.Theme.surface : "transparent"
                                Behavior on color {
                                    enabled: Ui.Theme.motionEnabled
                                    ColorAnimation {
                                        duration: 140
                                    }
                                }
                                border.color: parent.activeFocus ? Ui.Theme.accent : "transparent"
                            }
                        }
                    }
                }
                Item {
                    Layout.fillWidth: true
                }
                Text {
                    textFormat: Text.PlainText
                    visible: body.width > 620
                    text: window.viewState.appliedKind === "municipal" ? "SH4 · FOB" : "NCM · CIF"
                    color: Ui.Theme.muted
                    font.pixelSize: 11
                    HoverHandler {
                        id: basisHover
                    }
                    ToolTip.visible: basisHover.hovered
                    ToolTip.text: window.viewState.appliedKind === "municipal" ? "Município do domicílio fiscal do importador. Posição SH4 e valor FOB; universo mais amplo que os NCMs cadastrados." : "Importações agregadas por NCM, UF, país e URF."
                }
            }
            Ui.ImportFilters {
                id: filterPanel
                workspace: window
                backend: controller
            }
            Text {
                objectName: "importLocalUpdateNotice"
                visible: window.localActivityVisible
                Layout.fillWidth: true
                text: "Atualizando o recorte… Os indicadores mostram o último resultado concluído."
                color: Ui.Theme.muted
                font.pixelSize: 11
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                Accessible.role: Accessible.AlertMessage
            }
            GridLayout {
                id: metricsGrid
                objectName: "importSummaryMetrics"
                visible: window.viewState.loaded && window.activeSection === "summary"
                Layout.fillWidth: true
                columns: body.width > 930 ? 4 : body.width > 440 ? 2 : 1
                columnSpacing: 12
                rowSpacing: 12
                Repeater {
                    model: window.analysis.metrics
                    Ui.MetricCard {
                        required property var modelData
                        required property int index
                        objectName: "metricCard" + index
                        Layout.fillWidth: true
                        Layout.preferredHeight: 118
                        metric: modelData
                        emphasized: index === 0
                        iconName: ["chart", "weight", "price", "grid"][index]
                    }
                }
            }
            RowLayout {
                visible: window.viewState.loaded && window.activeSection === "summary"
                Layout.fillWidth: true
                spacing: 8
                Ui.ActionButton {
                    objectName: "importVisualTrend"
                    text: "Evolução mensal"
                    iconName: "chart"
                    primary: window.primaryVisual === "trend"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    onClicked: window.primaryVisual = "trend"
                }
                Ui.ActionButton {
                    id: visualOrigins
                    objectName: "importVisualOrigins"
                    text: "Origens"
                    iconName: "grid"
                    primary: window.primaryVisual === "origins"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    onClicked: window.primaryVisual = "origins"
                }
            }
            GridLayout {
                id: importChartsGrid
                objectName: "importSummaryVisual"
                visible: window.viewState.loaded && window.activeSection === "summary"
                Layout.fillWidth: true
                columns: 1
                columnSpacing: 16
                rowSpacing: 16
                Ui.ImportTrendPanel {
                    id: trendPanel
                    visible: window.primaryVisual === "trend"
                    buying: window.buying
                    shownKind: window.shownKind
                    onRevealRequested: control => window.reveal(control)
                    onExpandRequested: importChartDialog.open()
                    onValuesRequested: trendValuesDialog.open()
                }
                Rectangle {
                    objectName: "originsPanel"
                    visible: window.primaryVisual === "origins"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 420
                    Layout.minimumWidth: 0
                    Layout.preferredHeight: originsContent.implicitHeight + 36
                    color: Ui.Theme.surface
                    radius: Ui.Theme.radius
                    border.color: Ui.Theme.softLine
                    ColumnLayout {
                        id: originsContent
                        anchors.fill: parent
                        anchors.margins: 18
                        spacing: 14
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                textFormat: Text.PlainText
                                text: "Principais origens"
                                color: Ui.Theme.text
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                            }
                            Item {
                                Layout.fillWidth: true
                            }
                            Text {
                                textFormat: Text.PlainText
                                text: "% " + window.valueBasis
                                color: Ui.Theme.muted
                                font.pixelSize: 10
                            }
                        }
                        Ui.OriginChart {
                            objectName: "originChart"
                            Layout.fillWidth: true
                            rows: window.analysis.countries
                            interactive: window.viewState.loaded && !window.viewState.busy && !window.viewState.waiting
                            onOriginSelected: country => {
                                if (window.analysis.countries.some(row => row.label === country))
                                    controller.setFilters("country", [country]);
                            }
                        }
                        Item {
                            Layout.fillHeight: true
                        }
                        Text {
                            Layout.fillWidth: true
                            text: "Participação no valor " + window.valueBasis + " do recorte · até 6 origens. Selecione uma origem para aplicar o filtro."
                            color: Ui.Theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                            textFormat: Text.PlainText
                        }
                    }
                }
            }
            Ui.ImportBuyingPanel {
                id: buyingSection
                visible: window.viewState.loaded && window.activeSection === "buying"
                workspace: window
                backend: controller
            }
            Ui.ImportDocumentsPanel {
                id: documentsPanel
                visible: !window.viewState.demo && window.viewState.loaded && window.activeSection === "records" && (window.documentsExpanded || window.viewState.exportBusy || Boolean(window.viewState.exportError) || Boolean(window.viewState.exportMessage))
                workspace: window
                backend: controller
            }
            Ui.ImportRecordsPanel {
                id: recordsPanel
                visible: window.viewState.loaded && window.activeSection === "records"
                workspace: window
                backend: controller
                tableModel: recordModel
                onDetailsRequested: detailDialog.open()
            }
        }
    }

    Menu {
        id: quickExportMenu
        objectName: "quickExportMenu"
        parent: Overlay.overlay
        width: Math.min(310, window.hostWindow.width - 24)
        x: Math.max(12, Math.min(window.hostWindow.width - width - 12, window.exportAnchor.mapToItem(Overlay.overlay, 0, 0).x))
        y: window.exportAnchor.mapToItem(Overlay.overlay, 0, window.exportAnchor.height).y + 6
        background: Rectangle {
            color: Ui.Theme.surface
            border.color: Ui.Theme.line
            radius: 8
        }
        MenuItem {
            objectName: "quickExcel"
            text: "Excel · período completo"
            font.pixelSize: 13
            implicitHeight: 42
            onTriggered: window.saveDocument("excel")
        }
        MenuItem {
            objectName: "quickPowerBI"
            text: "Power BI · período completo"
            font.pixelSize: 13
            implicitHeight: 42
            onTriggered: window.saveDocument("powerbi")
        }
        MenuItem {
            objectName: "quickPDF"
            text: window.viewState.appliedKind !== "general" ? "PDF · use Dados gerais" : window.viewState.tableCount === "0" ? "PDF · sem registros nos filtros" : "PDF · filtros aplicados"
            font.pixelSize: 13
            implicitHeight: 42
            enabled: window.viewState.appliedKind === "general" && window.viewState.tableCount !== "0"
            onTriggered: window.saveDocument("pdf")
        }
    }
    Ui.ChartDialog {
        id: importChartDialog
        objectName: "importChartDialog"
        title: "Evolução mensal · " + (window.trendData.label || window.valueBasis)
        contextLabel: window.viewState.periodLabel + " · " + window.valueBasis + " · " + window.trendData.unit + "\n" + trendPanel.metricContext
        legendLabel: "Mensal" + (window.trendData.hasRolling ? " · " + window.trendData.rollingLabel + " (tracejada)" : "")
        points: window.trendData.points
        unit: window.trendData.unit
        precision: window.trendData.precision
        zoomed: trendPanel.zoomed
        allowNegative: trendPanel.allowNegative
    }
    Ui.TrendDialog {
        id: trendValuesDialog
        objectName: "trendValuesDialog"
        series: window.trendData
        contextLabel: window.viewState.periodLabel + (window.buying.productLabel ? " · " + window.buying.productLabel : "") + "\n" + trendPanel.metricContext
        onCopyRequested: copied = controller.copyTrendData(window.trendKey)
    }
    FileDialog {
        id: exportDialog
        objectName: "exportDialog"
        property string exportKind: "excel"
        fileMode: FileDialog.SaveFile
        currentFolder: controller.reportsFolder
        title: exportKind === "excel" ? "Salvar Excel" : exportKind === "pdf" ? "Salvar PDF" : "Salvar projeto Power BI"
        onAccepted: {
            window.navigate("documents");
            controller.exportTo(exportKind, selectedFile);
        }
    }
    Ui.AppDialog {
        id: detailDialog
        objectName: "detailDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(560, window.hostWindow.width - 40)
        modal: true
        title: "Detalhes do registro"
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 12
            Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: window.viewState.selectedTitle
                font.bold: true
                wrapMode: Text.WordWrap
                color: Ui.Theme.text
            }
            Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: window.viewState.selectedText
                wrapMode: Text.WordWrap
                color: Ui.Theme.text
                font.pixelSize: 12
                lineHeight: 1.3
            }
            Ui.ActionButton {
                text: "Copiar linha"
                enabled: window.viewState.selection >= 0
                onClicked: controller.copySelected()
            }
            Label {
                textFormat: Text.PlainText
                text: window.viewState.copyMessage
                color: Ui.Theme.muted
                font.pixelSize: 11
            }
        }
    }
}
