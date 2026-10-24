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
    property var importAnalysis: ({
            metrics: []
        })
    property var inventoryAnalysis: ({
            metrics: []
        })
    readonly property real pageMargin: width < 600 ? 18 : 28
    readonly property var summaryCards: {
        const cards = [];
        const imports = importAnalysis.metrics || [];
        const stock = inventoryAnalysis.metrics || [];
        if (importState.loaded && imports.length >= 2)
            cards.push({
                key: "imports",
                title: "Importações",
                icon: "chart",
                period: importState.periodLabel,
                basis: importState.appliedKind === "municipal" ? "Municipal · SH4 / FOB · US$" : "Geral · NCM / CIF · US$",
                scope: importState.filterSummary,
                status: importState.busy ? "Atualizando · último resultado concluído" : "Última consulta concluída",
                metrics: [imports[0], imports[1]]
            });
        if (inventoryState.loaded && stock.length)
            cards.push({
                key: "inventory",
                title: "Estoque",
                icon: "box",
                period: "Base em " + inventoryState.asOf,
                basis: "Saldo a custo · R$",
                scope: "Valores do recorte aplicado no módulo",
                status: inventoryState.busy || !inventoryState.current ? "Atualizando · último resultado concluído" : "Último recorte aplicado",
                metrics: stock.length > 4 ? [stock[0], stock[4]] : stock.slice(0, 2)
            });
        return cards;
    }
    signal moduleRequested(string key)

    function revealAction(item) {
        if (!item || !item.activeFocus)
            return;
        const top = item.mapToItem(homeScroll, 0, 0).y;
        const maximum = Math.max(0, homeScroll.contentHeight - homeScroll.height);
        if (top < 0)
            homeScroll.contentY = Math.max(0, homeScroll.contentY + top);
        else if (top + item.height > homeScroll.height)
            homeScroll.contentY = Math.min(maximum, homeScroll.contentY + top + item.height - homeScroll.height);
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
        contentHeight: content.implicitHeight + 56
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }
        ColumnLayout {
            id: content
            width: Math.min(1060, homeScroll.width - 2 * page.pageMargin)
            x: (homeScroll.width - width) / 2
            y: 26
            spacing: 20
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8
                Text {
                    text: "Visão geral"
                    textFormat: Text.PlainText
                    color: Ui.Theme.text
                    font.pixelSize: page.width < 600 ? 25 : 30
                    font.weight: Font.DemiBold
                    font.letterSpacing: -0.5
                }
                Text {
                    Layout.fillWidth: true
                    text: page.summaryCards.length ? "Os últimos resultados de cada módulo, com seus períodos e recortes." : "Abra um módulo para consultar os dados e acompanhar seus indicadores aqui."
                    textFormat: Text.PlainText
                    color: Ui.Theme.muted
                    font.pixelSize: 14
                    wrapMode: Text.WordWrap
                }
            }
            GridLayout {
                objectName: "homeSummary"
                visible: page.summaryCards.length > 0
                Layout.fillWidth: true
                columns: width >= 840 && page.summaryCards.length > 1 ? 2 : 1
                columnSpacing: 16
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
                        implicitHeight: summaryContent.implicitHeight + 36
                        radius: Ui.Theme.radius
                        color: Ui.Theme.surface
                        border.color: Ui.Theme.softLine
                        ColumnLayout {
                            id: summaryContent
                            x: 18
                            y: 18
                            width: parent.width - 36
                            spacing: 12
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10
                                Ui.Icon {
                                    name: summaryCard.modelData.icon
                                    color: Ui.Theme.accent
                                    Layout.preferredWidth: 20
                                    Layout.preferredHeight: 20
                                }
                                Text {
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 0
                                    text: summaryCard.modelData.title
                                    textFormat: Text.PlainText
                                    color: Ui.Theme.text
                                    font.pixelSize: 18
                                    font.weight: Font.DemiBold
                                }
                            }
                            Text {
                                objectName: "homeSummaryPeriod_" + summaryCard.modelData.key
                                Layout.fillWidth: true
                                text: summaryCard.modelData.period
                                textFormat: Text.PlainText
                                color: Ui.Theme.text
                                font.pixelSize: 12
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                Layout.fillWidth: true
                                text: summaryCard.modelData.basis
                                textFormat: Text.PlainText
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: width >= 350 ? 2 : 1
                                columnSpacing: 10
                                rowSpacing: 10
                                Repeater {
                                    model: summaryCard.modelData.metrics
                                    Ui.MetricCard {
                                        required property var modelData
                                        required property int index
                                        objectName: "homeMetric_" + summaryCard.modelData.key + "_" + index
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        metric: modelData
                                        emphasized: index === 0
                                        iconName: index === 0 ? summaryCard.modelData.icon : summaryCard.modelData.key === "imports" ? "weight" : "chart"
                                    }
                                }
                            }
                            Text {
                                objectName: "homeSummaryScope_" + summaryCard.modelData.key
                                Layout.fillWidth: true
                                text: summaryCard.modelData.scope
                                textFormat: Text.PlainText
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                objectName: "homeSummaryStatus_" + summaryCard.modelData.key
                                Layout.fillWidth: true
                                text: summaryCard.modelData.status
                                textFormat: Text.PlainText
                                color: Ui.Theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                            Ui.ActionButton {
                                id: summaryOpen
                                objectName: "homeSummaryOpen_" + summaryCard.modelData.key
                                Layout.fillWidth: true
                                text: "Abrir " + summaryCard.modelData.title
                                Accessible.name: "Abrir o recorte de " + summaryCard.modelData.title
                                onActiveFocusChanged: if (activeFocus)
                                    page.revealAction(summaryOpen)
                                onClicked: page.moduleRequested(summaryCard.modelData.key)
                            }
                        }
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                text: "Módulos"
                textFormat: Text.PlainText
                color: Ui.Theme.text
                font.pixelSize: 16
                font.weight: Font.DemiBold
            }
            Repeater {
                id: moduleCards
                model: page.platform.modules.filter(module => module.available)
                Button {
                    id: moduleButton
                    required property var modelData
                    objectName: "moduleCard_" + modelData.key
                    Layout.fillWidth: true
                    implicitHeight: Math.max(128, cardContent.implicitHeight + 40)
                    hoverEnabled: true
                    padding: 20
                    Accessible.name: "Abrir " + modelData.title
                    Accessible.description: modelData.description
                    onActiveFocusChanged: if (activeFocus)
                        page.revealAction(moduleButton)
                    onClicked: page.moduleRequested(modelData.key)
                    background: Rectangle {
                        radius: 10
                        color: moduleButton.hovered ? Ui.Theme.hover : Ui.Theme.surface
                        border.color: moduleButton.visualFocus ? Ui.Theme.accent : Ui.Theme.line
                        border.width: moduleButton.visualFocus ? 2 : 1
                        Behavior on color {
                            enabled: Ui.Theme.motionEnabled && page.visible
                            ColorAnimation {
                                duration: Ui.Theme.fast
                            }
                        }
                    }
                    contentItem: RowLayout {
                        id: cardContent
                        spacing: 14
                        Rectangle {
                            width: 42
                            height: 42
                            radius: 9
                            color: Ui.Theme.selected
                            Ui.Icon {
                                anchors.centerIn: parent
                                width: 23
                                height: 23
                                name: moduleButton.modelData.icon
                                color: Ui.Theme.accent
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 5
                            Text {
                                Layout.fillWidth: true
                                text: moduleButton.modelData.title
                                textFormat: Text.PlainText
                                font.pixelSize: 20
                                font.weight: Font.DemiBold
                                color: Ui.Theme.text
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                Layout.fillWidth: true
                                text: moduleButton.modelData.description
                                textFormat: Text.PlainText
                                font.pixelSize: 14
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
                                font.pixelSize: 13
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: moduleButton.modelData.key === "inventory" && (page.inventoryState.loaded || page.inventoryState.busy)
                                text: page.inventoryState.busy ? page.inventoryState.busyLabel : "Base " + page.inventoryState.asOf
                                textFormat: Text.PlainText
                                color: Ui.Theme.muted
                                font.pixelSize: 13
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }
            Text {
                Layout.topMargin: 8
                text: "Próximos módulos"
                textFormat: Text.PlainText
                color: Ui.Theme.muted
                font.pixelSize: 14
                font.weight: Font.Medium
            }
            GridLayout {
                Layout.fillWidth: true
                columns: page.width < 680 ? 1 : 2
                columnSpacing: 16
                rowSpacing: 16
                Repeater {
                    model: page.platform.modules.filter(module => !module.available)
                    Rectangle {
                        id: plannedCard
                        required property var modelData
                        objectName: "plannedModule_" + modelData.key
                        Layout.fillWidth: true
                        implicitHeight: plannedContent.implicitHeight + 36
                        radius: 10
                        color: "transparent"
                        border.color: Ui.Theme.softLine
                        Accessible.role: Accessible.StaticText
                        Accessible.name: modelData.title + ". Módulo planejado; ainda não disponível."
                        RowLayout {
                            id: plannedContent
                            x: 18
                            y: 18
                            width: parent.width - 36
                            spacing: 12
                            Ui.Icon {
                                Layout.alignment: Qt.AlignTop
                                Layout.topMargin: 2
                                name: plannedCard.modelData.icon
                                color: Ui.Theme.muted
                                Layout.preferredWidth: 21
                                Layout.preferredHeight: 21
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Text {
                                    Layout.fillWidth: true
                                    text: plannedCard.modelData.title
                                    textFormat: Text.PlainText
                                    font.pixelSize: 15
                                    font.weight: Font.Medium
                                    color: Ui.Theme.muted
                                    wrapMode: Text.WordWrap
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: plannedCard.modelData.description
                                    textFormat: Text.PlainText
                                    font.pixelSize: 13
                                    color: Ui.Theme.muted
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
