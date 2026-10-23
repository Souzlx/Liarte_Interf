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
    function restoreFocus() {
        if (!window.viewState.loaded)
            queryButton.forceActiveFocus();
        else
            tableView.forceActiveFocus();
    }
    readonly property var viewState: controller.presentation
    readonly property var analysis: controller.analysis
    readonly property var buying: analysis.procurement
    property int originLimit: 8
    property bool filtersExpanded: true
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
        filtersExpanded = true;
        Qt.callLater(() => {
            window.reveal(productFilter);
            productFilter.forceActiveFocus();
            productFilter.popup.open();
        });
    }
    readonly property var matchingOrigins: {
        if (!buying.comparable)
            return [];
        const rows = buying.origins.filter(row => row.kgValue >= Number(originMinWeight.currentValue || 0));
        const order = originOrder.currentValue || "volume";
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
    readonly property string activeSection: contentScroll.atYEnd && contentScroll.contentHeight > contentScroll.height ? "records" : contentScroll.contentY >= recordsPanel.y + body.y - 80 ? "records" : contentScroll.contentY >= buyingSection.y + body.y - 80 ? "buying" : "summary"
    function navigate(section) {
        const item = section === "records" ? recordsPanel : section === "buying" ? buyingSection : section === "documents" ? documentsPanel : queryPanel;
        const maximum = Math.max(0, contentScroll.contentHeight - contentScroll.height);
        const target = Math.max(0, Math.min(maximum, item.y + body.y - 12));
        navigation.stop();
        if (!Ui.Theme.motionEnabled)
            contentScroll.contentY = target;
        else {
            navigation.to = target;
            navigation.restart();
        }
    }
    NumberAnimation {
        id: navigation
        objectName: "navigationAnimation"
        target: contentScroll
        property: "contentY"
        duration: 240
        easing.type: Easing.OutCubic
    }
    NumberAnimation {
        id: recordsTransition
        objectName: "recordsTransition"
        target: tableView
        property: "opacity"
        from: 0.90
        to: 1
        duration: 140
        easing.type: Easing.OutCubic
    }
    Connections {
        target: recordModel
        function onContentChanged() {
            if (Ui.Theme.motionEnabled && tableView.visible && window.viewState.loaded)
                recordsTransition.restart();
            else {
                recordsTransition.stop();
                tableView.opacity = 1;
            }
        }
    }
    Connections {
        target: Ui.Theme
        function onMotionEnabledChanged() {
            if (!Ui.Theme.motionEnabled) {
                recordsTransition.stop();
                tableView.opacity = 1;
            }
            if (!Ui.Theme.motionEnabled && navigation.running) {
                const target = navigation.to;
                navigation.stop();
                contentScroll.contentY = Math.max(0, Math.min(target, contentScroll.contentHeight - contentScroll.height));
            }
        }
    }
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
    readonly property bool modalOpen: globalModalOpen || detailDialog.visible || exportDialog.visible || productFilter.popup.visible || countryFilter.popup.visible || stateFilter.popup.visible || portFilter.popup.visible || cityFilter.popup.visible || startPeriod.popup.visible || endPeriod.popup.visible || trendMetric.popup.visible || originMinWeight.popup.visible || originOrder.popup.visible || quickExportMenu.visible || trendValuesDialog.visible || tableProfile.popup.visible
    readonly property bool draftPeriod: viewState.loaded && (startPeriod.currentValue !== viewState.appliedStart || endPeriod.currentValue !== viewState.appliedEnd)
    readonly property bool collapsed: hostWindow.width < 1120
    readonly property var headers: viewState.headers
    readonly property string shownKind: viewState.appliedKind
    onShownKindChanged: {
        tableView.contentX = 0;
        tableView.contentY = 0;
    }
    readonly property string valueBasis: viewState.appliedKind === "municipal" ? "FOB" : "CIF"
    readonly property int pauseSeconds: viewState.sourcePauseSeconds || 0
    readonly property string pauseLabel: Math.floor(pauseSeconds / 60) + ":" + String(pauseSeconds % 60).padStart(2, "0")
    function userError(message) {
        if (message.includes("Comex Stat solicitou uma pausa"))
            return message;
        if (/HTTP\s*429|"code"\s*:\s*429/.test(message))
            return "O Comex Stat está com limite de consultas. Aguarde um pouco e tente novamente.";
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
        }
    }
    Shortcut {
        sequence: "Ctrl+F"
        enabled: window.visible && window.viewState.loaded && !window.modalOpen
        onActivated: {
            window.reveal(searchBox);
            searchBox.forceActiveFocus();
            searchBox.selectAll();
        }
    }
    Shortcut {
        sequence: "F5"
        enabled: window.visible && !window.viewState.busy && !window.viewState.metadataBusy && window.pauseSeconds === 0 && !window.modalOpen
        onActivated: controller.queryPeriod(startPeriod.currentValue, endPeriod.currentValue)
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
            Rectangle {
                id: queryPanel
                objectName: "queryPanel"
                Layout.fillWidth: true
                Layout.preferredHeight: queryBody.implicitHeight + 24
                color: Ui.Theme.surface
                radius: Ui.Theme.radius
                border.color: Ui.Theme.softLine
                ColumnLayout {
                    id: queryBody
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 12
                    GridLayout {
                        Layout.fillWidth: true
                        Layout.maximumWidth: 740
                        columns: body.width > 650 ? 3 : body.width > 470 ? 2 : 1
                        columnSpacing: 12
                        rowSpacing: 12
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 195
                            Layout.preferredWidth: 255
                            spacing: 5
                            Text {
                                textFormat: Text.PlainText
                                text: "Mês inicial"
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                            }
                            Ui.AppCombo {
                                id: startPeriod
                                objectName: "startPeriod"
                                onActiveFocusChanged: if (activeFocus)
                                    window.reveal(startPeriod)
                                Layout.fillWidth: true
                                model: controller.periods
                                enabled: !window.viewState.metadataBusy && !window.viewState.busy
                                currentIndex: model.findIndex(item => item.value === window.viewState.defaultStart)
                                Accessible.name: "Mês inicial"
                                onActivated: controller.setDraftPeriod("start", currentValue)
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 195
                            Layout.preferredWidth: 255
                            spacing: 5
                            Text {
                                textFormat: Text.PlainText
                                text: "Mês final"
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                            }
                            Ui.AppCombo {
                                id: endPeriod
                                objectName: "endPeriod"
                                onActiveFocusChanged: if (activeFocus)
                                    window.reveal(endPeriod)
                                Layout.fillWidth: true
                                model: controller.periods
                                enabled: !window.viewState.metadataBusy && !window.viewState.busy
                                currentIndex: model.findIndex(item => item.value === window.viewState.defaultEnd)
                                Accessible.name: "Mês final"
                                onActivated: controller.setDraftPeriod("end", currentValue)
                            }
                        }
                        Ui.ActionButton {
                            id: queryButton
                            objectName: "queryButton"
                            iconName: "search"
                            text: window.draftPeriod ? "Aplicar período" : window.viewState.busy && !window.viewState.localBusy ? "Consultando…" : "Consultar"
                            primary: true
                            Layout.fillWidth: true
                            Layout.preferredWidth: 155
                            Layout.minimumWidth: naturalWidth
                            Layout.alignment: Qt.AlignBottom
                            enabled: !window.viewState.busy && !window.viewState.metadataBusy && window.pauseSeconds === 0
                            onClicked: controller.queryPeriod(startPeriod.currentValue, endPeriod.currentValue)
                        }
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 6
                        Ui.ActionButton {
                            objectName: "cancelButton"
                            text: window.viewState.busy || window.viewState.waiting || window.viewState.metadataBusy ? "Cancelar" : window.viewState.demo ? "Todo o período" : "Último mês"
                            implicitWidth: Math.max(130, naturalWidth)
                            implicitHeight: 30
                            font.pixelSize: 11
                            subtle: !window.viewState.busy && !window.viewState.waiting
                            onClicked: {
                                if (window.viewState.metadataBusy)
                                    controller.cancelAvailability();
                                else if (window.viewState.busy || window.viewState.waiting)
                                    controller.cancel();
                                else {
                                    const last = controller.periods[controller.periods.length - 1].value;
                                    controller.queryPeriod(window.viewState.demo ? controller.periods[0].value : last, last);
                                }
                            }
                        }
                        Repeater {
                            model: [3, 6, 12]
                            Ui.ActionButton {
                                required property int modelData
                                objectName: "preset" + modelData
                                text: "Últimos " + modelData + " meses"
                                implicitHeight: 30
                                implicitWidth: Math.max(130, naturalWidth)
                                subtle: true
                                font.pixelSize: 11
                                enabled: !window.viewState.busy && !window.viewState.metadataBusy
                                onClicked: controller.setPeriodPreset(modelData)
                                ToolTip.visible: hovered
                                ToolTip.text: "Preencher meses publicados mais recentes. Confirme em Consultar."
                                ToolTip.delay: 500
                            }
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: (window.viewState.busy && !window.viewState.localBusy) || (window.viewState.waiting && !window.viewState.loaded) || window.viewState.metadataBusy || window.viewState.closing
                        spacing: 6
                        Ui.TaskProgress {
                            objectName: "queryProgress"
                            Layout.fillWidth: true
                            from: 0
                            to: 100
                            indeterminate: window.viewState.waiting || window.viewState.metadataBusy
                            value: window.viewState.progress
                            Accessible.name: "Progresso da consulta"
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                objectName: "queryStage"
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                text: window.viewState.metadataBusy ? "Verificando publicação do Comex Stat…" : window.viewState.waiting ? "Aplicando filtros…" : window.viewState.stage.replace(/\s*\(HTTP\s+\d{3}\)/g, "")
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                textFormat: Text.PlainText
                                text: window.viewState.progress + "%"
                                visible: !window.viewState.metadataBusy && !window.viewState.waiting
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                            }
                        }
                        Text {
                            textFormat: Text.PlainText
                            visible: window.viewState.loaded
                            Layout.fillWidth: true
                            text: "Exibindo o último resultado concluído."
                            color: Ui.Theme.warningText
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }
                    }
                    Text {
                        objectName: "queryError"
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        visible: window.pauseSeconds > 0 || window.viewState.error.length > 0 || window.viewState.metadataError.length > 0
                        text: window.pauseSeconds > 0 ? "O Comex Stat solicitou uma pausa. " + (window.viewState.busy || window.viewState.metadataBusy ? "Aguardando " + window.pauseLabel + " para uma nova tentativa automática." : "Aguarde " + window.pauseLabel + " antes de consultar novamente.") : window.userError(window.viewState.error || window.viewState.metadataError)
                        color: window.pauseSeconds > 0 ? Ui.Theme.muted : Ui.Theme.danger
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        Accessible.role: Accessible.AlertMessage
                    }
                    Text {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        visible: !window.viewState.busy && !window.viewState.waiting && window.viewState.stage.includes("cancelada")
                        text: window.viewState.stage
                        color: Ui.Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        textFormat: Text.PlainText
                        objectName: "draftPeriodNotice"
                        Layout.fillWidth: true
                        visible: window.draftPeriod && !window.viewState.busy
                        text: "Período alterado. Aplique para atualizar."
                        color: Ui.Theme.warningText
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                }
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
            Rectangle {
                id: filterPanel
                objectName: "filterPanel"
                visible: window.viewState.loaded
                Layout.fillWidth: true
                Layout.preferredHeight: filterBody.implicitHeight + 24
                color: Ui.Theme.surface
                radius: Ui.Theme.radius
                border.color: Ui.Theme.softLine
                ColumnLayout {
                    id: filterBody
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8
                    GridLayout {
                        id: filterActions
                        Layout.fillWidth: true
                        Layout.maximumWidth: Infinity
                        columns: parent.width >= toggleFilters.implicitWidth + filterExpansion.implicitWidth + clearFilters.implicitWidth + 3 * columnSpacing ? 4 : parent.width >= filterExpansion.implicitWidth + clearFilters.implicitWidth + columnSpacing ? 2 : 1
                        Ui.ActionButton {
                            id: toggleFilters
                            objectName: "toggleFilters"
                            Layout.columnSpan: filterActions.columns === 4 ? 1 : filterActions.columns
                            Layout.minimumWidth: naturalWidth
                            iconName: "filter"
                            text: "Filtros" + (window.viewState.filterCount ? " · " + window.viewState.filterCount : "")
                            implicitHeight: 30
                            subtle: true
                            Accessible.name: window.filtersExpanded ? "Recolher filtros" : "Expandir filtros"
                            onClicked: window.filtersExpanded = !window.filtersExpanded
                        }
                        Item {
                            visible: filterActions.columns === 4
                            Layout.fillWidth: true
                        }
                        Ui.ActionButton {
                            id: filterExpansion
                            objectName: "filterExpansion"
                            text: window.filtersExpanded ? "Recolher" : "Expandir"
                            implicitHeight: 30
                            implicitWidth: Math.max(90, naturalWidth)
                            Layout.minimumWidth: implicitWidth
                            subtle: true
                            onClicked: window.filtersExpanded = !window.filtersExpanded
                        }
                        Ui.ActionButton {
                            id: clearFilters
                            objectName: "clearFilters"
                            text: "Limpar"
                            implicitHeight: 28
                            implicitWidth: Math.max(80, naturalWidth)
                            Layout.minimumWidth: implicitWidth
                            subtle: true
                            enabled: window.viewState.filterCount > 0 || searchBox.text.length > 0
                            onClicked: controller.clearFilters()
                        }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        visible: window.filtersExpanded
                        columns: body.width > 970 ? 4 : body.width > 550 ? 2 : 1
                        columnSpacing: 12
                        rowSpacing: 10
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 340
                            spacing: 6
                            Text {
                                textFormat: Text.PlainText
                                text: window.viewState.kind === "municipal" ? "Posição SH4" : "Produto / NCM"
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                            }
                            Ui.MultiCombo {
                                id: productFilter
                                objectName: "productFilter"
                                onActiveFocusChanged: if (activeFocus)
                                    window.reveal(productFilter)
                                Layout.fillWidth: true
                                model: controller.products
                                currentValues: window.viewState.ncmValues
                                Accessible.name: "Filtrar por produto ou código"
                                onValuesChosen: values => controller.setFilters("ncm", values)
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 210
                            spacing: 6
                            Text {
                                textFormat: Text.PlainText
                                text: "País de origem"
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                            }
                            Ui.MultiCombo {
                                id: countryFilter
                                objectName: "countryFilter"
                                onActiveFocusChanged: if (activeFocus)
                                    window.reveal(countryFilter)
                                Layout.fillWidth: true
                                model: controller.countries
                                currentValues: window.viewState.countryValues
                                Accessible.name: "Filtrar por país"
                                onValuesChosen: values => controller.setFilters("country", values)
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 115
                            spacing: 6
                            Text {
                                textFormat: Text.PlainText
                                text: "UF"
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                            }
                            Ui.MultiCombo {
                                id: stateFilter
                                objectName: "stateFilter"
                                onActiveFocusChanged: if (activeFocus)
                                    window.reveal(stateFilter)
                                Layout.fillWidth: true
                                model: controller.states
                                currentValues: window.viewState.stateValues
                                Accessible.name: "Filtrar por UF"
                                onValuesChosen: values => controller.setFilters("state", values)
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 245
                            spacing: 6
                            Text {
                                textFormat: Text.PlainText
                                text: window.viewState.kind === "municipal" ? "Município fiscal" : "Porto / URF"
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                            }
                            Ui.MultiCombo {
                                id: portFilter
                                objectName: "portFilter"
                                visible: window.viewState.kind !== "municipal"
                                onActiveFocusChanged: if (activeFocus)
                                    window.reveal(portFilter)
                                Layout.fillWidth: true
                                model: controller.ports
                                currentValues: window.viewState.portValues
                                Accessible.name: "Filtrar por porto ou URF"
                                onValuesChosen: values => controller.setFilters("port", values)
                            }
                            Ui.MultiCombo {
                                id: cityFilter
                                objectName: "cityFilter"
                                visible: window.viewState.kind === "municipal"
                                onActiveFocusChanged: if (activeFocus)
                                    window.reveal(cityFilter)
                                Layout.fillWidth: true
                                model: controller.cities
                                currentValues: window.viewState.cityValues
                                Accessible.name: "Filtrar por município fiscal"
                                onValuesChosen: values => controller.setFilters("city", values)
                            }
                        }
                    }
                    Flow {
                        visible: window.activeFilters.length > 0
                        Layout.fillWidth: true
                        spacing: 6
                        Repeater {
                            model: window.activeFilters
                            Ui.FilterChip {
                                required property var modelData
                                objectName: "activeFilter_" + modelData.key
                                caption: modelData.caption
                                description: modelData.description
                                onRemoved: controller.setFilters(modelData.key, [])
                            }
                        }
                    }
                }
            }
            GridLayout {
                id: metricsGrid
                visible: window.viewState.loaded
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
            GridLayout {
                visible: window.viewState.loaded
                Layout.fillWidth: true
                columns: body.width > 930 ? 2 : 1
                columnSpacing: 16
                rowSpacing: 16
                Rectangle {
                    objectName: "trendPanel"
                    Layout.fillWidth: true
                    Layout.preferredWidth: 660
                    Layout.preferredHeight: 398
                    color: Ui.Theme.surface
                    radius: Ui.Theme.radius
                    border.color: Ui.Theme.softLine
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 18
                        spacing: 8
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                textFormat: Text.PlainText
                                text: "Evolução mensal"
                                color: Ui.Theme.text
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                            }
                            Item {
                                Layout.fillWidth: true
                            }
                            Ui.AppCombo {
                                id: trendMetric
                                objectName: "trendMetric"
                                property string selectedMetricKey: "value"
                                Layout.preferredWidth: 140
                                implicitHeight: 34
                                font.pixelSize: 12
                                Accessible.name: "Indicador do gráfico mensal"
                                onActivated: selectedMetricKey = currentValue
                                onModelChanged: Qt.callLater(() => {
                                    const matchingIndex = model.findIndex(item => item.value === selectedMetricKey);
                                    currentIndex = matchingIndex >= 0 ? matchingIndex : 0;
                                })
                                model: window.shownKind === "municipal" ? [
                                    {
                                        label: "Valor FOB",
                                        value: "value"
                                    },
                                    {
                                        label: "FOB/kg",
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
                                        label: "CIF/kg",
                                        value: "price"
                                    },
                                    {
                                        label: "FOB/kg",
                                        value: "fob"
                                    },
                                    {
                                        label: "Frete/kg",
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
                                    window.reveal(trendMetric)
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: window.trendData.unit
                                color: Ui.Theme.muted
                                font.pixelSize: 10
                                textFormat: Text.PlainText
                            }
                            Item {
                                Layout.fillWidth: true
                            }
                            Text {
                                text: window.trendData.change
                                color: Ui.Theme.text
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                                textFormat: Text.PlainText
                            }
                            Text {
                                text: window.trendData.comparison
                                color: Ui.Theme.muted
                                font.pixelSize: 10
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                Layout.maximumWidth: 160
                            }
                        }
                        GridLayout {
                            id: trendActions
                            Layout.fillWidth: true
                            Layout.maximumWidth: Infinity
                            columns: parent.width >= priceScale.implicitWidth + openTrendValues.implicitWidth + 2 * columnSpacing ? 3 : 1
                            Ui.AppCheck {
                                id: priceScale
                                objectName: "priceScale"
                                Layout.minimumWidth: 0
                                Layout.maximumWidth: trendActions.parent.width
                                wrapLabel: true
                                text: "Ampliar variação"
                                visible: ["price", "fob", "freight"].includes(window.trendKey)
                                font.pixelSize: 11
                                ToolTip.visible: hovered
                                ToolTip.text: "Ajusta o eixo para comparar pequenas diferenças. Os valores permanecem iguais."
                            }
                            Item {
                                visible: trendActions.columns === 3
                                Layout.fillWidth: true
                            }
                            Ui.ActionButton {
                                id: openTrendValues
                                objectName: "openTrendValues"
                                text: "Ver valores"
                                iconName: "grid"
                                implicitHeight: 30
                                implicitWidth: Math.max(132, naturalWidth)
                                Layout.minimumWidth: implicitWidth
                                font.pixelSize: 11
                                subtle: true
                                onClicked: trendValuesDialog.open()
                            }
                        }
                        Ui.LinePlot {
                            id: monthlyChart
                            objectName: "monthlyChart"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            points: window.trendData.points
                            unit: window.trendData.unit
                            precision: window.trendData.precision
                            allowNegative: window.trendKey === "valueChange"
                            zoomed: priceScale.checked && ["price", "fob", "freight"].includes(window.trendKey)
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 7
                            Rectangle {
                                width: 16
                                height: 2
                                color: Ui.Theme.accent
                            }
                            Text {
                                text: "Mensal"
                                color: Ui.Theme.muted
                                font.pixelSize: 10
                            }
                            Item {
                                width: 8
                                height: 1
                            }
                            Item {
                                visible: window.trendData.hasRolling
                                width: 16
                                height: 2
                                Row {
                                    spacing: 2
                                    Repeater {
                                        model: 3
                                        Rectangle {
                                            width: 4
                                            height: 2
                                            color: Ui.Theme.muted
                                        }
                                    }
                                }
                            }
                            Text {
                                visible: window.trendData.hasRolling
                                text: window.trendData.rollingLabel
                                color: Ui.Theme.muted
                                font.pixelSize: 10
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                            Text {
                                visible: monthlyChart.width > 440 && window.trendData.periodChange !== "—"
                                text: "Período: " + (window.trendData.periodChange || "—")
                                color: Ui.Theme.muted
                                font.pixelSize: 10
                                textFormat: Text.PlainText
                            }
                        }
                        Text {
                            objectName: "trendReadout"
                            Layout.fillWidth: true
                            text: monthlyChart.readout.replace("\n", " · ")
                            textFormat: Text.PlainText
                            color: Ui.Theme.text
                            font.pixelSize: 11
                            elide: Text.ElideRight
                            Accessible.name: monthlyChart.readout
                        }
                        Text {
                            objectName: "axisScaleNotice"
                            visible: monthlyChart.croppedAxis
                            Layout.fillWidth: true
                            text: "Eixo ajustado · a escala não começa em zero"
                            color: Ui.Theme.muted
                            font.pixelSize: 10
                            textFormat: Text.PlainText
                        }
                    }
                }
                Rectangle {
                    objectName: "originsPanel"
                    Layout.fillWidth: true
                    Layout.preferredWidth: 420
                    Layout.preferredHeight: 398
                    color: Ui.Theme.surface
                    radius: Ui.Theme.radius
                    border.color: Ui.Theme.softLine
                    ColumnLayout {
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
                            Layout.fillHeight: true
                            rows: window.analysis.countries
                        }
                    }
                }
            }
            ColumnLayout {
                id: buyingSection
                objectName: "buyingSection"
                visible: window.viewState.loaded
                Layout.fillWidth: true
                spacing: 12
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: "Referências de compra"
                        color: Ui.Theme.text
                        font.pixelSize: 15
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                    Item {
                        Layout.fillWidth: true
                    }
                    Text {
                        text: window.buying.productLabel
                        color: Ui.Theme.muted
                        font.pixelSize: 11
                        textFormat: Text.PlainText
                        Layout.maximumWidth: 175
                        Layout.preferredWidth: 140
                        wrapMode: Text.WordWrap
                    }
                }
                GridLayout {
                    Layout.fillWidth: true
                    columns: body.width > 930 ? 4 : body.width > 440 ? 2 : 1
                    columnSpacing: 12
                    rowSpacing: 12
                    Repeater {
                        model: window.buying.cards
                        Ui.MetricCard {
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
                    radius: Ui.Theme.radius
                    color: Ui.Theme.surface
                    border.color: Ui.Theme.softLine
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
                                color: Ui.Theme.text
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                                textFormat: Text.PlainText
                            }
                            Item {
                                Layout.fillWidth: true
                            }
                            Ui.AppCombo {
                                id: originMinWeight
                                objectName: "originMinWeight"
                                visible: window.buying.comparable
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
                                onCurrentValueChanged: window.originLimit = 8
                                Accessible.name: "Peso mínimo por país no comparador"
                                ToolTip.visible: hovered
                                ToolTip.text: "Peso acumulado por país no período. Altera apenas este comparador; os totais e documentos mantêm seus filtros."
                                ToolTip.delay: 600
                                onActiveFocusChanged: if (activeFocus)
                                    window.reveal(originMinWeight)
                            }
                            Ui.AppCombo {
                                id: originOrder
                                objectName: "originOrder"
                                visible: window.buying.comparable
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
                                onCurrentValueChanged: window.originLimit = 8
                            }
                            Ui.ActionButton {
                                objectName: "chooseComparisonProduct"
                                visible: !window.buying.comparable && !window.buying.empty
                                text: "Selecionar produto"
                                primary: false
                                Layout.preferredWidth: 165
                                implicitHeight: 34
                                onClicked: window.chooseProduct()
                            }
                        }
                        Text {
                            visible: !window.buying.comparable
                            Layout.fillWidth: true
                            text: window.buying.empty ? "Nenhuma importação para estes filtros." : "Escolha um produto para comparar as origens."
                            wrapMode: Text.WordWrap
                            textFormat: Text.PlainText
                            color: Ui.Theme.muted
                            font.pixelSize: 12
                        }
                        Ui.ActionButton {
                            objectName: "recoverEmptyFilters"
                            visible: window.buying.empty && window.viewState.filterCount > 0
                            text: "Limpar filtros"
                            implicitHeight: 34
                            onClicked: controller.clearFilters()
                        }
                        Ui.OriginComparison {
                            id: priceComparison
                            objectName: "priceComparison"
                            visible: window.buying.comparable
                            Layout.fillWidth: true
                            rows: window.matchingOrigins.slice(0, window.originLimit)
                            basis: window.valueBasis
                            reference: window.buying.reference === undefined ? null : window.buying.reference
                            onOriginChosen: name => controller.setFilters("country", [name])
                        }
                        Text {
                            visible: window.buying.comparable && priceComparison.rows.length === 0
                            Layout.fillWidth: true
                            text: "Nenhuma origem atinge o peso mínimo selecionado."
                            wrapMode: Text.WordWrap
                            color: Ui.Theme.muted
                            font.pixelSize: 12
                            textFormat: Text.PlainText
                        }
                        Text {
                            visible: window.buying.comparable
                            Layout.fillWidth: true
                            text: priceComparison.rows.length + " de " + window.matchingOrigins.length + " origens · Média do recorte: " + window.buying.referenceText + "/kg" + (priceComparison.graphic ? " (traço vertical)" : "")
                            wrapMode: Text.WordWrap
                            color: Ui.Theme.muted
                            font.pixelSize: 11
                            textFormat: Text.PlainText
                        }
                        Ui.ActionButton {
                            objectName: "moreOrigins"
                            visible: window.matchingOrigins.length > window.originLimit
                            text: "Mostrar mais origens"
                            implicitHeight: 32
                            font.pixelSize: 11
                            onClicked: window.originLimit += 8
                        }
                        Text {
                            visible: window.buying.comparable
                            Layout.fillWidth: true
                            text: window.buying.range
                            wrapMode: Text.WordWrap
                            color: Ui.Theme.muted
                            font.pixelSize: 11
                            textFormat: Text.PlainText
                        }
                        Ui.ActionButton {
                            objectName: "toggleMethodology"
                            text: window.methodologyExpanded ? "Ocultar explicação" : "Como interpretar"
                            iconName: "info"
                            subtle: true
                            implicitHeight: 30
                            font.pixelSize: 11
                            onClicked: window.methodologyExpanded = !window.methodologyExpanded
                        }
                        Text {
                            visible: window.methodologyExpanded
                            Layout.fillWidth: true
                            text: window.buying.note
                            wrapMode: Text.WordWrap
                            color: Ui.Theme.muted
                            font.pixelSize: 11
                            textFormat: Text.PlainText
                        }
                    }
                }
            }
            Rectangle {
                id: documentsPanel
                objectName: "documentsPanel"
                visible: !window.viewState.demo && window.viewState.loaded
                Layout.fillWidth: true
                Layout.preferredHeight: exportBody.implicitHeight + 32
                color: Ui.Theme.surface
                border.color: Ui.Theme.softLine
                radius: Ui.Theme.radius
                ColumnLayout {
                    id: exportBody
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 10
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            textFormat: Text.PlainText
                            text: "Documentos"
                            color: Ui.Theme.text
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                        Item {
                            Layout.fillWidth: true
                        }
                        Ui.ActionButton {
                            objectName: "openReportFolder"
                            visible: !window.viewState.exportBusy && window.viewState.lastExport.length > 0
                            iconName: "folder"
                            text: ""
                            implicitWidth: 30
                            implicitHeight: 28
                            leftPadding: 6
                            rightPadding: 6
                            subtle: true
                            Accessible.name: "Abrir pasta do relatório"
                            ToolTip.text: "Abrir pasta · " + window.viewState.lastExport
                            onClicked: controller.openExport(true)
                            ToolTip.visible: hovered
                            ToolTip.delay: 400
                        }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        Layout.maximumWidth: 740
                        columns: body.width > 670 ? 3 : body.width > 370 ? 2 : 1
                        columnSpacing: 10
                        rowSpacing: 8
                        Ui.ActionButton {
                            objectName: "exportExcel"
                            Layout.fillWidth: true
                            iconName: "file"
                            text: "Baixar Excel"
                            enabled: window.viewState.canExport && !window.draftPeriod && !window.viewState.exportBusy
                            onClicked: window.saveDocument("excel")
                            ToolTip.visible: hovered
                            ToolTip.text: "Todo o período e cadastro. Os filtros da análise não reduzem a planilha."
                            ToolTip.delay: 400
                        }
                        Ui.ActionButton {
                            objectName: "exportPowerBI"
                            Layout.fillWidth: true
                            iconName: "chart"
                            text: "Baixar Power BI"
                            enabled: window.viewState.canExport && !window.draftPeriod && !window.viewState.exportBusy
                            onClicked: window.saveDocument("powerbi")
                            ToolTip.visible: hovered
                            ToolTip.text: "Projeto Power BI e Excel do período completo, em ZIP. Extraia antes de abrir no Power BI Desktop."
                            ToolTip.delay: 400
                        }
                        Ui.ActionButton {
                            objectName: "exportPdf"
                            Layout.fillWidth: true
                            iconName: "download"
                            text: "Baixar PDF"
                            enabled: window.viewState.canExport && !window.draftPeriod && !window.viewState.exportBusy && window.viewState.appliedKind === "general" && window.viewState.tableCount !== "0"
                            onClicked: window.saveDocument("pdf")
                            ToolTip.visible: hovered
                            ToolTip.text: window.viewState.appliedKind === "municipal" ? "O PDF comercial utiliza a base geral." : "Seleção atual de toda a tabela. Acima de 1.000 kg, sem aeroportos, em A4."
                            ToolTip.delay: 400
                        }
                    }
                    Text {
                        textFormat: Text.PlainText
                        visible: window.viewState.filterCount > 0 || window.viewState.search.length > 0
                        Layout.fillWidth: true
                        text: "Excel e BI: período completo. PDF: seleção atual."
                        color: Ui.Theme.muted
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
                    RowLayout {
                        visible: window.viewState.exportBusy
                        Layout.fillWidth: true
                        Ui.TaskProgress {
                            objectName: "documentProgress"
                            Layout.fillWidth: true
                            from: 0
                            to: 100
                            value: window.viewState.exportProgress
                            Accessible.name: "Progresso do documento"
                        }
                        Ui.ActionButton {
                            objectName: "cancelExport"
                            iconName: "close"
                            text: "Cancelar"
                            implicitHeight: 32
                            onClicked: controller.cancelExport()
                        }
                    }
                    Text {
                        textFormat: Text.PlainText
                        visible: window.viewState.exportBusy
                        Layout.fillWidth: true
                        text: window.viewState.exportStage
                        color: Ui.Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        textFormat: Text.PlainText
                        visible: window.viewState.exportError.length > 0
                        Layout.fillWidth: true
                        text: window.viewState.exportError
                        color: Ui.Theme.danger
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        Accessible.role: Accessible.AlertMessage
                    }
                    Text {
                        textFormat: Text.PlainText
                        visible: window.viewState.exportMessage.length > 0
                        Layout.fillWidth: true
                        text: window.viewState.exportMessage
                        color: Ui.Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                }
            }
            Rectangle {
                id: recordsPanel
                objectName: "recordsPanel"
                visible: window.viewState.loaded
                Layout.fillWidth: true
                Layout.preferredHeight: tableBody.implicitHeight + 34
                color: Ui.Theme.surface
                radius: Ui.Theme.radius
                border.color: Ui.Theme.softLine
                ColumnLayout {
                    id: tableBody
                    anchors {
                        fill: parent
                        margins: 17
                    }
                    spacing: 10
                    GridLayout {
                        Layout.fillWidth: true
                        columns: body.width > 970 ? 3 : body.width > 550 ? 2 : 1
                        columnSpacing: 12
                        rowSpacing: 10
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            Text {
                                textFormat: Text.PlainText
                                text: "Registros"
                                color: Ui.Theme.text
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                            }
                            Text {
                                textFormat: Text.PlainText
                                text: window.viewState.tableRange
                                color: Ui.Theme.muted
                                font.pixelSize: 10
                            }
                        }
                        Ui.AppCombo {
                            id: tableProfile
                            objectName: "tableProfile"
                            Layout.preferredWidth: 180
                            implicitHeight: 36
                            model: [
                                {
                                    label: "Visão de compras",
                                    value: "buying"
                                },
                                {
                                    label: "Todas as colunas",
                                    value: "full"
                                }
                            ]
                            Accessible.name: "Colunas da tabela"
                            onCurrentValueChanged: {
                                recordModel.setProfile(currentValue);
                                Qt.callLater(() => {
                                    tableView.contentX = 0;
                                    tableView.forceLayout();
                                });
                            }
                            Component.onCompleted: recordModel.setProfile(currentValue)
                        }
                        TextField {
                            id: searchBox
                            objectName: "searchBox"
                            Layout.fillWidth: true
                            Layout.columnSpan: parent.columns === 2 ? 2 : 1
                            Layout.preferredWidth: 360
                            Layout.maximumWidth: 400
                            Layout.alignment: Qt.AlignRight
                            implicitHeight: 39
                            text: window.viewState.search
                            placeholderText: "Buscar na tabela…"
                            maximumLength: 250
                            rightPadding: 38
                            Ui.ActionButton {
                                objectName: "clearSearch"
                                visible: searchBox.text.length > 0
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.rightMargin: 3
                                implicitWidth: 30
                                implicitHeight: 30
                                leftPadding: 6
                                rightPadding: 6
                                subtle: true
                                text: ""
                                iconName: "close"
                                Accessible.name: "Limpar busca da tabela"
                                onClicked: controller.setFilter("search", "")
                            }
                            color: Ui.Theme.text
                            placeholderTextColor: Ui.Theme.muted
                            font.pixelSize: 12
                            leftPadding: 11
                            Accessible.name: "Buscar somente na tabela, sem alterar indicadores e gráficos"
                            onTextEdited: controller.setFilter("search", text)
                            background: Rectangle {
                                radius: 5
                                color: Ui.Theme.surface
                                border.color: parent.activeFocus ? Ui.Theme.accent : Ui.Theme.line
                                border.width: parent.activeFocus ? 2 : 1
                            }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 385
                        objectName: "recordsViewport"
                        clip: true
                        border.color: Ui.Theme.line
                        color: Ui.Theme.surface
                        HorizontalHeaderView {
                            id: tableHeader
                            anchors {
                                top: parent.top
                                left: parent.left
                                right: parent.right
                            }
                            height: 42
                            syncView: tableView
                            clip: true
                            delegate: Rectangle {
                                required property int column
                                required property string display
                                objectName: "tableHeader" + column
                                clip: true
                                implicitWidth: tableView.columnWidthProvider(column)
                                implicitHeight: 42
                                color: Ui.Theme.subtle
                                Text {
                                    textFormat: Text.PlainText
                                    anchors {
                                        fill: parent
                                        leftMargin: 11
                                        rightMargin: 11
                                    }
                                    verticalAlignment: Text.AlignVCenter
                                    text: display + (window.viewState.sortColumn === tableView.sourceColumn(column) ? window.viewState.descending ? " ↓" : " ↑" : "")
                                    horizontalAlignment: tableView.numericColumn(column) ? Text.AlignRight : Text.AlignLeft
                                    color: Ui.Theme.text
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }
                                TapHandler {
                                    onTapped: controller.sortByColumn(tableView.sourceColumn(column))
                                }
                                Accessible.role: Accessible.ColumnHeader
                                Accessible.name: "Ordenar por " + display
                                Accessible.onPressAction: controller.sortByColumn(tableView.sourceColumn(column))
                            }
                        }
                        TableView {
                            id: tableView
                            objectName: "recordsTable"
                            onVisibleChanged: {
                                if (!visible) {
                                    recordsTransition.stop();
                                    opacity = 1;
                                }
                            }
                            anchors {
                                top: tableHeader.bottom
                                left: parent.left
                                right: parent.right
                                bottom: parent.bottom
                            }
                            clip: true
                            model: recordModel
                            reuseItems: true
                            boundsBehavior: Flickable.StopAtBounds
                            columnSpacing: 1
                            rowSpacing: 1
                            property var columnSpecs: recordModel.viewColumns
                            function sourceColumn(column) {
                                return columnSpecs[column] ? columnSpecs[column].source : -1;
                            }
                            function numericColumn(column) {
                                return columnSpecs[column] ? columnSpecs[column].numeric : false;
                            }
                            onColumnSpecsChanged: forceLayout()
                            property bool compactMode: window.viewState.compact
                            columnWidthProvider: column => columnSpecs[column] ? columnSpecs[column].width : 120
                            rowHeightProvider: row => compactMode ? 32 : 40
                            onCompactModeChanged: forceLayout()
                            onWidthChanged: forceLayout()
                            ScrollBar.horizontal: ScrollBar {
                                policy: ScrollBar.AsNeeded
                            }
                            ScrollBar.vertical: ScrollBar {
                                policy: ScrollBar.AsNeeded
                            }
                            Keys.onPressed: event => {
                                let count = recordModel.rowCount();
                                if (event.key === Qt.Key_Down && count) {
                                    const row = Math.min(count - 1, window.viewState.selection + 1);
                                    controller.selectRow(row);
                                    positionViewAtRow(row, TableView.Contain);
                                    event.accepted = true;
                                } else if (event.key === Qt.Key_Up && count) {
                                    const row = Math.max(0, window.viewState.selection - 1);
                                    controller.selectRow(row);
                                    positionViewAtRow(row, TableView.Contain);
                                    event.accepted = true;
                                } else if (count && [Qt.Key_Home, Qt.Key_End, Qt.Key_PageDown, Qt.Key_PageUp].includes(event.key)) {
                                    const step = event.key === Qt.Key_PageDown ? 8 : -8;
                                    const row = event.key === Qt.Key_Home ? 0 : event.key === Qt.Key_End ? count - 1 : Math.max(0, Math.min(count - 1, window.viewState.selection + step));
                                    controller.selectRow(row);
                                    positionViewAtRow(row, TableView.Contain);
                                    event.accepted = true;
                                } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && window.viewState.selection >= 0) {
                                    detailDialog.open();
                                    event.accepted = true;
                                } else if (event.key === Qt.Key_C && event.modifiers & Qt.ControlModifier) {
                                    controller.copySelected();
                                    event.accepted = true;
                                }
                            }
                            delegate: Rectangle {
                                required property int row
                                required property int column
                                required property string display
                                required property string originalText
                                clip: true
                                implicitWidth: tableView.columnWidthProvider(column)
                                implicitHeight: window.viewState.compact ? 32 : 40
                                color: window.viewState.selection === row ? Ui.Theme.selected : row % 2 ? Ui.Theme.subtle : Ui.Theme.surface
                                Text {
                                    id: cellText
                                    textFormat: Text.PlainText
                                    anchors {
                                        fill: parent
                                        leftMargin: 11
                                        rightMargin: 11
                                    }
                                    text: display
                                    color: Ui.Theme.text
                                    font.pixelSize: 12
                                    verticalAlignment: Text.AlignVCenter
                                    horizontalAlignment: tableView.numericColumn(column) ? Text.AlignRight : Text.AlignLeft
                                    elide: Text.ElideRight
                                }
                                TapHandler {
                                    onTapped: {
                                        controller.selectRow(row);
                                        tableView.forceActiveFocus();
                                    }
                                    onDoubleTapped: {
                                        controller.selectRow(row);
                                        detailDialog.open();
                                    }
                                }
                                HoverHandler {
                                    id: cellHover
                                }
                                ToolTip.visible: cellHover.hovered && cellText.truncated
                                ToolTip.text: originalText
                                ToolTip.delay: 450
                                Accessible.role: Accessible.Cell
                                Accessible.name: (tableView.columnSpecs[column] || {
                                        label: ""
                                    }).label + ": " + originalText
                                Accessible.onPressAction: controller.selectRow(row)
                            }
                            Text {
                                textFormat: Text.PlainText
                                anchors.centerIn: parent
                                visible: window.viewState.loaded && window.viewState.tableCount === "0"
                                text: "Nenhum registro para esta seleção."
                                color: Ui.Theme.muted
                                font.pixelSize: 13
                            }
                            Text {
                                textFormat: Text.PlainText
                                anchors.centerIn: parent
                                visible: !window.viewState.loaded
                                text: "Consulte um período para visualizar os registros."
                                color: Ui.Theme.muted
                                font.pixelSize: 12
                            }
                        }
                        Ui.TaskProgress {
                            objectName: "localProgress"
                            anchors.top: tableHeader.bottom
                            anchors.left: parent.left
                            anchors.right: parent.right
                            height: 2
                            z: 2
                            indeterminate: true
                            visible: window.localActivityVisible
                            Accessible.name: "Atualizando registros"
                        }
                    }
                    GridLayout {
                        columns: body.width > 480 ? 2 : 1
                        columnSpacing: 12
                        rowSpacing: 9
                        Layout.fillWidth: true
                        RowLayout {
                            Layout.fillWidth: true
                            Ui.AppCombo {
                                objectName: "pageSize"
                                Layout.preferredWidth: 125
                                model: [
                                    {
                                        label: "25 linhas",
                                        value: 25
                                    },
                                    {
                                        label: "50 linhas",
                                        value: 50
                                    },
                                    {
                                        label: "100 linhas",
                                        value: 100
                                    },
                                    {
                                        label: "200 linhas",
                                        value: 200
                                    }
                                ]
                                currentIndex: model.findIndex(item => item.value === window.viewState.pageSize)
                                Accessible.name: "Linhas por página"
                                onActivated: controller.setPageSize(currentValue)
                            }
                            Text {
                                textFormat: Text.PlainText
                                text: "Página " + window.viewState.page + " de " + window.viewState.pages
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                            }
                        }
                        RowLayout {
                            Layout.alignment: Qt.AlignRight
                            Layout.fillWidth: true
                            Item {
                                Layout.fillWidth: true
                            }
                            Ui.ActionButton {
                                objectName: "firstPage"
                                iconName: "first"
                                implicitWidth: 36
                                leftPadding: 8
                                rightPadding: 8
                                text: ""
                                Accessible.name: "Primeira página"
                                enabled: window.viewState.loaded && !window.viewState.busy && !window.viewState.waiting && window.viewState.page > 1
                                onClicked: controller.setPage(1)
                                ToolTip.visible: hovered
                                ToolTip.text: "Primeira página"
                                ToolTip.delay: 450
                            }
                            Ui.ActionButton {
                                objectName: "previousPage"
                                iconName: "left"
                                implicitWidth: 42
                                text: ""
                                Accessible.name: "Página anterior"
                                enabled: window.viewState.loaded && !window.viewState.waiting && window.viewState.page > 1 && !window.viewState.busy
                                onClicked: controller.setPage(window.viewState.page - 1)
                            }
                            Ui.ActionButton {
                                objectName: "nextPage"
                                iconName: "right"
                                implicitWidth: 42
                                text: ""
                                Accessible.name: "Próxima página"
                                enabled: window.viewState.loaded && !window.viewState.waiting && window.viewState.page < window.viewState.pages && !window.viewState.busy
                                onClicked: controller.setPage(window.viewState.page + 1)
                            }
                            Ui.ActionButton {
                                objectName: "lastPage"
                                iconName: "last"
                                implicitWidth: 36
                                leftPadding: 8
                                rightPadding: 8
                                text: ""
                                Accessible.name: "Última página"
                                enabled: window.viewState.loaded && !window.viewState.busy && !window.viewState.waiting && window.viewState.page < window.viewState.pages
                                onClicked: controller.setPage(window.viewState.pages)
                                ToolTip.visible: hovered
                                ToolTip.text: "Última página"
                                ToolTip.delay: 450
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            text: window.viewState.copyMessage || window.viewState.selectedTitle || ""
                            color: Ui.Theme.muted
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                        Ui.ActionButton {
                            objectName: "detailsButton"
                            text: "Detalhes"
                            enabled: window.viewState.selection >= 0
                            onClicked: detailDialog.open()
                        }
                    }
                }
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
    Ui.TrendDialog {
        id: trendValuesDialog
        objectName: "trendValuesDialog"
        series: window.trendData
        contextLabel: window.viewState.periodLabel + (window.buying.productLabel ? " · " + window.buying.productLabel : "")
        onCopyRequested: copied = controller.copyTrendData(window.trendKey)
    }
    FileDialog {
        id: exportDialog
        objectName: "exportDialog"
        property string exportKind: "excel"
        fileMode: FileDialog.SaveFile
        currentFolder: controller.reportsFolder
        title: exportKind === "excel" ? "Salvar Excel" : exportKind === "pdf" ? "Salvar PDF" : "Salvar projeto Power BI"
        onAccepted: controller.exportTo(exportKind, selectedFile)
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
