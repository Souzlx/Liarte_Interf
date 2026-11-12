import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components" as Ui

FocusScope {
    id: page
    objectName: "homePage"
    required property var platform
    required property var importState
    required property var inventoryState
    property var importAnalysis: ({metrics: []})
    property var inventoryAnalysis: ({metrics: []})
    readonly property real pageMargin: width < 600 ? 18 : width < 1000 ? 24 : 36
    readonly property var summaryCards: {
        const cards = [];
        const imports = importAnalysis.metrics || [];
        const stock = inventoryAnalysis.metrics || [];
        if (importState.loaded && imports.length >= 2)
            cards.push({
                key: "imports", title: "Importações", icon: "chart",
                period: importState.periodLabel,
                basis: importState.appliedKind === "municipal" ? "Municipal · FOB · US$" : "CIF · US$",
                scope: importState.filterSummary,
                status: importState.busy ? "Atualizando · último resultado concluído" : "Consulta concluída",
                metrics: [imports[0], imports[1]]
            });
        if (inventoryState.loaded && stock.length)
            cards.push({
                key: "inventory", title: "Estoque", icon: "box",
                period: "Posição em " + inventoryState.asOf,
                basis: "Saldo a custo · R$",
                scope: "Valores do recorte aplicado no módulo",
                status: inventoryState.busy || !inventoryState.current ? "Atualizando · último resultado concluído" : "Último recorte aplicado",
                metrics: stock.slice(0, 2)
            });
        return cards;
    }
    readonly property var historySummary: inventoryAnalysis.historySummary || ({})
    readonly property var activityRows: inventoryState.loaded ? (inventoryAnalysis.activityChart || []) : []
    property var focusRevealTarget: null
    signal moduleRequested(string key)

    function revealAction(item, includeReadout) {
        if (!item || (!item.activeFocus && !includeReadout))
            return;
        focusRevealTarget = item;
        const top = item.mapToItem(homeScroll, 0, 0).y;
        const maximum = Math.max(0, homeScroll.contentHeight - homeScroll.height);
        if (top < 0)
            homeScroll.contentY = Math.max(0, homeScroll.contentY + top);
        else if (top + item.height > homeScroll.height)
            homeScroll.contentY = Math.min(maximum, homeScroll.contentY + top + item.height - homeScroll.height);
    }
    function revealAfterLayout() {
        const item = focusRevealTarget;
        if (!visible || !item)
            return;
        if (item.activeFocus)
            revealAction(item);
        else if (item === homeStockTrendReadout && homeStockTrend.activeFocus)
            revealAction(item, true);
    }
    function focusFirst() {
        const actions = [];
        for (let i = 0; i < summaryRepeater.count; ++i)
            actions.push(summaryRepeater.itemAt(i).openAction);
        for (let i = 0; i < moduleCards.count; ++i)
            actions.push(moduleCards.itemAt(i));
        let nearest = null, distance = Infinity;
        for (const item of actions) {
            if (!item || !item.visible || !item.enabled)
                continue;
            const top = item.mapToItem(homeScroll, 0, 0).y;
            if (top >= 0 && top + item.height <= homeScroll.height) {
                item.forceActiveFocus(Qt.TabFocusReason);
                revealAction(item);
                return;
            }
            const gap = top < 0 ? -top : top + item.height - homeScroll.height;
            if (gap < distance) {
                nearest = item;
                distance = gap;
            }
        }
        if (nearest) {
            nearest.forceActiveFocus(Qt.TabFocusReason);
            revealAction(nearest);
        }
    }

    Flickable {
        id: homeScroll
        objectName: "homeScroll"
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: content.implicitHeight + 2 * page.pageMargin
        // A route can receive focus before Qt polishes its compact layout.
        // Recheck the focused control against the final content bounds.
        onContentHeightChanged: Qt.callLater(page.revealAfterLayout)
        onHeightChanged: Qt.callLater(page.revealAfterLayout)
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        ColumnLayout {
            id: content
            width: Math.min(1220, homeScroll.width - 2 * page.pageMargin)
            x: (homeScroll.width - width) / 2
            y: page.pageMargin
            spacing: 18

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8
                Text {
                    text: "PAINEL DE GESTÃO / VISÃO GERAL"
                    textFormat: Text.PlainText
                    color: Ui.Theme.accent
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                    font.letterSpacing: 1.3
                }
                Text {
                    Layout.fillWidth: true
                    text: "Visão geral das operações"
                    textFormat: Text.PlainText
                    color: Ui.Theme.text
                    font.pixelSize: page.width < 600 ? 25 : 28
                    font.weight: Font.DemiBold
                    font.letterSpacing: -0.6
                    wrapMode: Text.WordWrap
                }
                Text {
                    Layout.fillWidth: true
                    text: page.summaryCards.length ? "Indicadores das últimas análises concluídas, com os períodos e recortes de cada fonte." : "Abra um módulo para consultar os dados e acompanhar seus indicadores aqui."
                    textFormat: Text.PlainText
                    color: Ui.Theme.muted
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                }
            }

            GridLayout {
                objectName: "homeSummary"
                visible: page.summaryCards.length > 0
                Layout.fillWidth: true
                columns: width >= 840 && page.summaryCards.length > 1 ? 2 : 1
                columnSpacing: 14
                rowSpacing: 16
                Repeater {
                    id: summaryRepeater
                    model: page.summaryCards
                    Rectangle {
                        id: summaryCard
                        required property var modelData
                        readonly property alias openAction: summaryOpen
                        objectName: "homeSummaryCard_" + modelData.key
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        Layout.alignment: Qt.AlignTop
                        implicitHeight: summaryContent.implicitHeight
                        color: "transparent"
                        ColumnLayout {
                            id: summaryContent
                            width: parent.width
                            spacing: 7
                            GridLayout {
                                Layout.fillWidth: true
                                columns: width >= 350 ? 2 : 1
                                columnSpacing: 14
                                rowSpacing: 12
                                Repeater {
                                    model: summaryCard.modelData.metrics
                                    Ui.MetricCard {
                                        required property var modelData
                                        required property int index
                                        objectName: "homeMetric_" + summaryCard.modelData.key + "_" + index
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        metric: modelData
                                        iconName: index === 0 ? summaryCard.modelData.icon : summaryCard.modelData.key === "imports" ? "weight" : "box"
                                    }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 0
                                    spacing: 3
                                    Text {
                                        objectName: "homeSummaryPeriod_" + summaryCard.modelData.key
                                        Layout.fillWidth: true
                                        text: summaryCard.modelData.period + " · " + summaryCard.modelData.basis
                                        textFormat: Text.PlainText
                                        color: Ui.Theme.muted
                                        font.pixelSize: 10
                                        wrapMode: Text.WordWrap
                                    }
                                    Text {
                                        objectName: "homeSummaryScope_" + summaryCard.modelData.key
                                        Layout.fillWidth: true
                                        text: summaryCard.modelData.scope
                                        textFormat: Text.PlainText
                                        color: Ui.Theme.muted
                                        font.pixelSize: 10
                                        wrapMode: Text.WordWrap
                                    }
                                    Text {
                                        objectName: "homeSummaryStatus_" + summaryCard.modelData.key
                                        Layout.fillWidth: true
                                        text: summaryCard.modelData.status
                                        textFormat: Text.PlainText
                                        color: Ui.Theme.muted
                                        font.pixelSize: 10
                                        wrapMode: Text.WordWrap
                                    }
                                }
                                Ui.ActionButton {
                                    id: summaryOpen
                                    objectName: "homeSummaryOpen_" + summaryCard.modelData.key
                                    text: "Abrir " + summaryCard.modelData.title
                                    subtle: true
                                    font.pixelSize: 11
                                    Accessible.name: "Abrir o recorte de " + summaryCard.modelData.title
                                    onActiveFocusChanged: if (activeFocus) page.revealAction(summaryOpen)
                                    onClicked: page.moduleRequested(summaryCard.modelData.key)
                                }
                            }
                        }
                    }
                }
            }

            GridLayout {
                id: analysisGrid
                Layout.fillWidth: true
                columns: width >= 900 ? 2 : 1
                columnSpacing: 14
                rowSpacing: 14
                Rectangle {
                    objectName: "homeStockHistoryCard"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 740
                    implicitHeight: stockHistoryContent.implicitHeight + 40
                    radius: Ui.Theme.radius
                    color: Ui.Theme.surface
                    border.color: Ui.Theme.softLine
                    ColumnLayout {
                        id: stockHistoryContent
                        x: 20
                        y: 20
                        width: parent.width - 40
                        spacing: 8
                        Text {
                            Layout.fillWidth: true
                            text: "Evolução do estoque"
                            textFormat: Text.PlainText
                            color: Ui.Theme.text
                            font.pixelSize: 16
                            font.weight: Font.DemiBold
                        }
                        Text {
                            Layout.fillWidth: true
                            text: page.inventoryState.loaded ? (page.historySummary.period || "Sem fechamentos no recorte") + " · " + (page.inventoryAnalysis.historicalScope || "") : "Fechamentos a custo"
                            textFormat: Text.PlainText
                            color: Ui.Theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        RowLayout {
                            visible: page.inventoryState.loaded
                            Layout.fillWidth: true
                            Text {
                                Layout.fillWidth: true
                                text: page.historySummary.value || "—"
                                textFormat: Text.PlainText
                                color: Ui.Theme.text
                                font.pixelSize: 22
                                font.weight: Font.DemiBold
                            }
                            Text {
                                Layout.fillWidth: true
                                text: page.historySummary.change || ""
                                textFormat: Text.PlainText
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                                horizontalAlignment: Text.AlignRight
                                wrapMode: Text.WordWrap
                            }
                        }
                        Ui.StockPlot {
                            id: homeStockTrend
                            objectName: "homeStockTrend"
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            Layout.preferredHeight: 230
                            points: page.inventoryState.loaded ? (page.inventoryAnalysis.plotTrend || []) : []
                            movingAverage: false
                            onActiveFocusChanged: if (activeFocus) page.revealAction(homeStockTrendReadout, true)
                            onReadoutChanged: if (activeFocus) Qt.callLater(() => page.revealAction(homeStockTrendReadout, true))
                        }
                        Text {
                            id: homeStockTrendReadout
                            objectName: "homeStockTrendReadout"
                            Layout.fillWidth: true
                            visible: text.length > 0
                            text: homeStockTrend.readout
                            textFormat: Text.PlainText
                            color: Ui.Theme.text
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            Layout.fillWidth: true
                            text: page.inventoryState.loaded ? "R$ a custo · lacunas indicam meses sem fechamento · use o cursor ou as setas para ler os valores." : "Os dados aparecem após abrir Estoque e concluir a leitura da base."
                            textFormat: Text.PlainText
                            color: Ui.Theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                    }
                }
                Rectangle {
                    objectName: "homeStockActivityCard"
                    Layout.fillWidth: true
                    Layout.fillHeight: analysisGrid.columns === 2
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 420
                    implicitHeight: activityContent.implicitHeight + 40
                    radius: Ui.Theme.radius
                    color: Ui.Theme.surface
                    border.color: Ui.Theme.softLine
                    ColumnLayout {
                        id: activityContent
                        x: 20
                        y: 20
                        width: parent.width - 40
                        spacing: 9
                        Text {
                            Layout.fillWidth: true
                            text: "Capital por última venda"
                            textFormat: Text.PlainText
                            color: Ui.Theme.text
                            font.pixelSize: 16
                            font.weight: Font.DemiBold
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            Layout.fillWidth: true
                            text: page.inventoryState.loaded ? "Capital positivo · referência em " + page.inventoryState.asOf : "Distribuição do recorte de estoque"
                            textFormat: Text.PlainText
                            color: Ui.Theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        Repeater {
                            model: page.activityRows
                            ColumnLayout {
                                id: activityRow
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 12
                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.topMargin: 10
                                    spacing: 9
                                    Rectangle {
                                        Layout.preferredWidth: 7
                                        Layout.preferredHeight: 7
                                        radius: 4
                                        color: Ui.Theme.accent
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        text: activityRow.modelData.name
                                        textFormat: Text.PlainText
                                        color: Ui.Theme.muted
                                        font.pixelSize: 12
                                        wrapMode: Text.WordWrap
                                    }
                                    Text {
                                        Layout.maximumWidth: activityContent.width * 0.55
                                        text: activityRow.modelData.display
                                        textFormat: Text.PlainText
                                        color: Ui.Theme.text
                                        font.pixelSize: 12
                                        font.weight: Font.DemiBold
                                        wrapMode: Text.WrapAnywhere
                                        horizontalAlignment: Text.AlignRight
                                    }
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: 1
                                    color: Ui.Theme.softLine
                                }
                            }
                        }
                        Text {
                            visible: !page.inventoryState.loaded
                            Layout.fillWidth: true
                            Layout.topMargin: 30
                            Layout.bottomMargin: 30
                            text: "Métrica indisponível\nCarregue os dados em Estoque."
                            textFormat: Text.PlainText
                            color: Ui.Theme.muted
                            font.pixelSize: 13
                            wrapMode: Text.WordWrap
                            lineHeight: 1.5
                        }
                        Text {
                            Layout.fillWidth: true
                            Layout.topMargin: 8
                            text: "Última venda observada não representa a idade dos lotes."
                            textFormat: Text.PlainText
                            color: Ui.Theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }

            Rectangle {
                objectName: "homeWorkspacesCard"
                Layout.fillWidth: true
                implicitHeight: workspacesContent.implicitHeight + 40
                radius: Ui.Theme.radius
                color: Ui.Theme.surface
                border.color: Ui.Theme.softLine
                ColumnLayout {
                    id: workspacesContent
                    x: 20
                    y: 20
                    width: parent.width - 40
                    spacing: 12
                    Text {
                        text: "Áreas de trabalho"
                        textFormat: Text.PlainText
                        color: Ui.Theme.text
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Consulte os dados e refine a análise no módulo de origem."
                        textFormat: Text.PlainText
                        color: Ui.Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    Repeater {
                        id: moduleCards
                        model: page.platform.modules.filter(module => module.available)
                        Button {
                            id: moduleButton
                            required property var modelData
                            objectName: "moduleCard_" + modelData.key
                            Layout.fillWidth: true
                            implicitHeight: Math.max(72, cardContent.implicitHeight + 24)
                            hoverEnabled: true
                            padding: 12
                            Accessible.name: "Abrir " + modelData.title
                            Accessible.description: modelData.description
                            onActiveFocusChanged: if (activeFocus) page.revealAction(moduleButton)
                            onClicked: page.moduleRequested(modelData.key)
                            background: Rectangle {
                                radius: 8
                                color: moduleButton.hovered ? Ui.Theme.hover : Ui.Theme.surface
                                border.color: moduleButton.visualFocus ? Ui.Theme.accent : Ui.Theme.softLine
                                border.width: moduleButton.visualFocus ? 2 : 1
                                Behavior on color {
                                    enabled: Ui.Theme.motionEnabled && page.visible
                                    ColorAnimation { duration: Ui.Theme.fast }
                                }
                            }
                            contentItem: RowLayout {
                                id: cardContent
                                spacing: 14
                                Rectangle {
                                    Layout.preferredWidth: 38
                                    Layout.preferredHeight: 38
                                    radius: 10
                                    color: Ui.Theme.selected
                                    Ui.Icon {
                                        anchors.centerIn: parent
                                        width: 20
                                        height: 20
                                        name: moduleButton.modelData.icon
                                        color: Ui.Theme.accent
                                    }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 0
                                    spacing: 4
                                    Text {
                                        Layout.fillWidth: true
                                        text: moduleButton.modelData.title
                                        textFormat: Text.PlainText
                                        font.pixelSize: 13
                                        font.weight: Font.DemiBold
                                        color: Ui.Theme.text
                                        wrapMode: Text.WordWrap
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: moduleButton.modelData.description
                                        textFormat: Text.PlainText
                                        font.pixelSize: 11
                                        color: Ui.Theme.muted
                                        wrapMode: Text.WordWrap
                                    }
                                    Text {
                                        objectName: moduleButton.modelData.key === "imports" ? "homeImportContext" : "unusedImportContext_" + moduleButton.modelData.key
                                        Layout.fillWidth: true
                                        visible: moduleButton.modelData.key === "imports" && (page.importState.loaded || page.importState.busy || page.importState.exportBusy || page.importState.error.length > 0 || page.importState.exportError.length > 0)
                                        text: page.importState.error.length || page.importState.exportError.length ? "Há uma pendência na última operação. Abra o módulo para ver os detalhes." : page.importState.exportBusy ? "Preparando documento · " + page.importState.exportProgress + "%" : page.importState.busy ? (page.importState.localBusy ? "Atualizando a visualização" : "Consulta em andamento · " + page.importState.progress + "%") : page.importState.periodLabel
                                        textFormat: Text.PlainText
                                        color: page.importState.error.length || page.importState.exportError.length ? Ui.Theme.danger : Ui.Theme.muted
                                        wrapMode: Text.WordWrap
                                        font.pixelSize: 11
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        visible: moduleButton.modelData.key === "inventory" && (page.inventoryState.loaded || page.inventoryState.busy)
                                        text: page.inventoryState.busy ? page.inventoryState.busyLabel : "Base " + page.inventoryState.asOf
                                        textFormat: Text.PlainText
                                        color: Ui.Theme.muted
                                        font.pixelSize: 11
                                        wrapMode: Text.WordWrap
                                    }
                                }
                                Ui.Icon {
                                    name: "right"
                                    color: Ui.Theme.muted
                                    Layout.preferredWidth: 16
                                    Layout.preferredHeight: 16
                                }
                            }
                        }
                    }
                }
            }
            Repeater {
                model: page.platform.modules.filter(module => !module.available)
                Rectangle {
                    id: plannedCard
                    required property var modelData
                    objectName: "plannedModule_" + modelData.key
                    Layout.fillWidth: true
                    implicitHeight: plannedContent.implicitHeight + 20
                    radius: 8
                    color: "transparent"
                    Accessible.role: Accessible.StaticText
                    Accessible.name: modelData.title + ". Módulo planejado; ainda não disponível."
                    RowLayout {
                        id: plannedContent
                        x: 10
                        y: 10
                        width: parent.width - 20
                        spacing: 10
                        Ui.Icon {
                            name: plannedCard.modelData.icon
                            color: Ui.Theme.muted
                            Layout.preferredWidth: 16
                            Layout.preferredHeight: 16
                        }
                        Text {
                            Layout.fillWidth: true
                            text: plannedCard.modelData.title + " · Planejado"
                            textFormat: Text.PlainText
                            font.pixelSize: 11
                            color: Ui.Theme.muted
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }
    }
}
