pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: queryPanel
    required property var workspace
    required property var backend
    readonly property bool fieldsVisible: !queryPanel.workspace.viewState.loaded || queryPanel.workspace.periodExpanded || queryPanel.workspace.draftPeriod
    readonly property string startValue: startPeriod.currentValue || ""
    readonly property string endValue: endPeriod.currentValue || ""
    readonly property bool modalOpen: startPeriod.popup.visible || endPeriod.popup.visible
    readonly property var historyState: queryPanel.workspace.historyState || ({})
    readonly property bool queryTaskBusy: (queryPanel.workspace.viewState.busy && !queryPanel.workspace.viewState.localBusy)
        || (queryPanel.workspace.viewState.waiting && !queryPanel.workspace.viewState.loaded)
        || queryPanel.workspace.viewState.metadataBusy || queryPanel.workspace.viewState.closing
    readonly property bool historyTaskBusy: !queryPanel.workspace.viewState.loaded && !queryTaskBusy && !!historyState.busy
    readonly property int loadingProgress: Math.max(0, Math.min(100, Math.round(historyTaskBusy ? historyState.progress || 0 : queryPanel.workspace.viewState.progress || 0)))
    function focusQuery() {
        queryPanel.workspace.periodExpanded = true;
        Qt.callLater(() => {
            queryPanel.workspace.reveal(queryButton);
            queryButton.forceActiveFocus();
        });
    }
    objectName: "queryPanel"
    Layout.fillWidth: true
    Layout.preferredHeight: queryBody.implicitHeight + 32
    color: Theme.surface
    radius: Theme.radius
    border.color: Theme.softLine
    ColumnLayout {
        id: queryBody
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12
        GridLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            columns: width >= 520 ? 2 : 1
            columnSpacing: 12
            rowSpacing: 8
            RowLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 12
                Rectangle {
                    Layout.preferredWidth: 34
                    Layout.preferredHeight: 34
                    radius: Theme.controlRadius
                    color: Theme.selected
                    Icon {
                        anchors.centerIn: parent
                        width: 17
                        height: 17
                        name: "grid"
                        color: Theme.accent
                    }
                }
                Text {
                    objectName: "importAppliedPeriod"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: queryPanel.workspace.viewState.loaded
                        ? queryPanel.workspace.viewState.periodLabel
                        : "Selecione os meses da consulta"
                    textFormat: Text.PlainText
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    color: Theme.text
                    wrapMode: Text.WordWrap
                    verticalAlignment: Text.AlignVCenter
                }
            }
            ActionButton {
                objectName: "editImportPeriod"
                visible: queryPanel.workspace.viewState.loaded
                text: queryPanel.fieldsVisible ? "Recolher" : "Período"
                Layout.fillWidth: parent.columns === 1
                Layout.minimumWidth: 0
                Layout.alignment: parent.columns === 1 ? Qt.AlignLeft : Qt.AlignRight | Qt.AlignVCenter
                implicitHeight: 34
                subtle: true
                Accessible.name: queryPanel.fieldsVisible ? "Recolher período" : "Alterar período da consulta"
                ToolTip.visible: hovered
                ToolTip.text: Accessible.name
                ToolTip.delay: 500
                onClicked: queryPanel.workspace.periodExpanded = !queryPanel.workspace.periodExpanded
            }
        }
        GridLayout {
            visible: queryPanel.fieldsVisible
            Layout.fillWidth: true
            Layout.maximumWidth: 900
            columns: queryPanel.width > 650 ? 3 : queryPanel.width > 470 ? 2 : 1
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
                    color: Theme.muted
                    font.pixelSize: 11
                }
                AppCombo {
                    id: startPeriod
                    objectName: "startPeriod"
                    onActiveFocusChanged: if (activeFocus)
                        queryPanel.workspace.reveal(startPeriod)
                    Layout.fillWidth: true
                    model: queryPanel.backend.periods
                    enabled: !queryPanel.workspace.viewState.metadataBusy && !queryPanel.workspace.viewState.busy
                    currentIndex: model.findIndex(item => item.value === queryPanel.workspace.viewState.defaultStart)
                    Accessible.name: "Mês inicial"
                    onActivated: queryPanel.backend.setDraftPeriod("start", currentValue)
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
                    color: Theme.muted
                    font.pixelSize: 11
                }
                AppCombo {
                    id: endPeriod
                    objectName: "endPeriod"
                    onActiveFocusChanged: if (activeFocus)
                        queryPanel.workspace.reveal(endPeriod)
                    Layout.fillWidth: true
                    model: queryPanel.backend.periods
                    enabled: !queryPanel.workspace.viewState.metadataBusy && !queryPanel.workspace.viewState.busy
                    currentIndex: model.findIndex(item => item.value === queryPanel.workspace.viewState.defaultEnd)
                    Accessible.name: "Mês final"
                    onActivated: queryPanel.backend.setDraftPeriod("end", currentValue)
                }
            }
            ActionButton {
                id: queryButton
                objectName: "queryButton"
                iconName: "search"
                text: queryPanel.workspace.resumingQuery && !queryPanel.workspace.viewState.busy ? "Retomar consulta" : queryPanel.workspace.draftPeriod ? "Aplicar período" : queryPanel.workspace.viewState.busy && !queryPanel.workspace.viewState.localBusy ? "Consultando…" : "Consultar"
                primary: true
                Layout.fillWidth: true
                Layout.preferredWidth: 155
                Layout.minimumWidth: naturalWidth
                Layout.alignment: Qt.AlignBottom
                enabled: !queryPanel.workspace.viewState.busy && !queryPanel.workspace.viewState.metadataBusy && (queryPanel.workspace.viewState.historicalMode || queryPanel.workspace.pauseSeconds === 0)
                onClicked: queryPanel.backend.queryPeriod(startPeriod.currentValue, endPeriod.currentValue)
            }
        }
        Flow {
            visible: queryPanel.fieldsVisible || queryPanel.workspace.viewState.metadataBusy || (queryPanel.workspace.viewState.busy && !queryPanel.workspace.viewState.localBusy) || queryPanel.workspace.localActivityVisible || (queryPanel.workspace.viewState.waiting && !queryPanel.workspace.viewState.loaded)
            Layout.fillWidth: true
            spacing: 6
            ActionButton {
                objectName: "restartIncompleteQuery"
                visible: queryPanel.workspace.resumingQuery
                enabled: !queryPanel.workspace.viewState.busy && !queryPanel.workspace.viewState.metadataBusy && queryPanel.workspace.pauseSeconds === 0
                text: "Reiniciar consulta"
                implicitHeight: 30
                subtle: true
                onClicked: queryPanel.backend.restartQueryPeriod(startPeriod.currentValue, endPeriod.currentValue)
                ToolTip.visible: hovered
                ToolTip.text: "Descartar a parte incompleta e consultar as duas bases novamente."
                ToolTip.delay: 500
            }
            ActionButton {
                objectName: "cancelButton"
                text: queryPanel.workspace.viewState.busy || queryPanel.workspace.viewState.waiting || queryPanel.workspace.viewState.metadataBusy ? "Cancelar" : queryPanel.workspace.viewState.demo ? "Todo o período" : "Último mês"
                implicitWidth: Math.max(130, naturalWidth)
                implicitHeight: 30
                font.pixelSize: 11
                subtle: !queryPanel.workspace.viewState.busy && !queryPanel.workspace.viewState.waiting
                onClicked: {
                    if (queryPanel.workspace.viewState.metadataBusy)
                        queryPanel.backend.cancelAvailability();
                    else if (queryPanel.workspace.viewState.busy || queryPanel.workspace.viewState.waiting)
                        queryPanel.backend.cancel();
                    else {
                        const last = queryPanel.backend.periods[queryPanel.backend.periods.length - 1].value;
                        queryPanel.backend.queryPeriod(queryPanel.workspace.viewState.demo ? queryPanel.backend.periods[0].value : last, last);
                    }
                }
            }
            Repeater {
                model: [3, 6, 12]
                ActionButton {
                    required property int modelData
                    objectName: "preset" + modelData
                    visible: queryPanel.fieldsVisible
                    text: "Últimos " + modelData + " meses"
                    implicitHeight: 30
                    implicitWidth: Math.max(130, naturalWidth)
                    subtle: true
                    font.pixelSize: 11
                    enabled: !queryPanel.workspace.viewState.busy && !queryPanel.workspace.viewState.metadataBusy
                    onClicked: queryPanel.backend.setPeriodPreset(modelData)
                    ToolTip.visible: hovered
                    ToolTip.text: "Preencher meses publicados mais recentes. Confirme em Consultar."
                    ToolTip.delay: 500
                }
            }
        }
        ColumnLayout {
            objectName: "queryLoading"
            Layout.fillWidth: true
            visible: queryPanel.queryTaskBusy || queryPanel.historyTaskBusy
            spacing: 6
            TaskProgress {
                objectName: "queryProgress"
                Layout.fillWidth: true
                from: 0
                to: 100
                indeterminate: !queryPanel.historyTaskBusy && (queryPanel.workspace.viewState.waiting || queryPanel.workspace.viewState.metadataBusy || queryPanel.workspace.viewState.closing || queryPanel.workspace.viewState.localBusy)
                value: queryPanel.loadingProgress
                Accessible.name: "Carregamento das importações"
            }
            Text {
                objectName: "queryPercentage"
                Layout.fillWidth: true
                textFormat: Text.PlainText
                text: queryPanel.loadingProgress + "%"
                visible: queryPanel.historyTaskBusy || (!queryPanel.workspace.viewState.metadataBusy && !queryPanel.workspace.viewState.waiting && !queryPanel.workspace.viewState.closing && !queryPanel.workspace.viewState.localBusy)
                color: Theme.muted
                font.pixelSize: 11
                horizontalAlignment: Text.AlignRight
            }
        }
        Text {
            objectName: "queryError"
            textFormat: Text.PlainText
            Layout.fillWidth: true
            visible: (!queryPanel.workspace.viewState.historicalMode && queryPanel.workspace.pauseSeconds > 0) || queryPanel.workspace.viewState.error.length > 0 || queryPanel.workspace.viewState.metadataError.length > 0
            text: !queryPanel.workspace.viewState.historicalMode && queryPanel.workspace.pauseSeconds > 0 ? queryPanel.workspace.pauseMessage() : queryPanel.workspace.userError(queryPanel.workspace.viewState.error || queryPanel.workspace.viewState.metadataError)
            color: (!queryPanel.workspace.viewState.historicalMode && queryPanel.workspace.pauseSeconds > 0) || queryPanel.workspace.sourcePauseError(queryPanel.workspace.viewState.error || queryPanel.workspace.viewState.metadataError) ? Theme.muted : Theme.danger
            font.pixelSize: 12
            wrapMode: Text.WordWrap
            Accessible.role: Accessible.AlertMessage
        }
        Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            visible: !queryPanel.workspace.viewState.busy && !queryPanel.workspace.viewState.waiting && queryPanel.workspace.viewState.stage.includes("cancelada")
            text: queryPanel.workspace.viewState.stage
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        Text {
            textFormat: Text.PlainText
            objectName: "draftPeriodNotice"
            Layout.fillWidth: true
            visible: queryPanel.workspace.draftPeriod && !queryPanel.workspace.viewState.busy
            text: "Período alterado. Aplique para atualizar."
            color: Theme.warningText
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
    }
}
