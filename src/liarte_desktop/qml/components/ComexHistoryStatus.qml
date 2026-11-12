pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    required property var owner
    required property var workspace
    readonly property var historyState: owner ? owner.state : ({ enabled: false })
    readonly property bool covered: Boolean(historyState.coverageStart && historyState.coverageEnd)
    readonly property int pauseSeconds: Number(historyState.pauseSeconds || 0)
    readonly property string pauseLabel: Math.floor(pauseSeconds / 60) + ":" + String(pauseSeconds % 60).padStart(2, "0")
    function monthLabel(value) {
        if (!value || value.length < 7)
            return "";
        return value.slice(5, 7) + "/" + value.slice(0, 4);
    }
    function timeLabel(value) {
        if (!value)
            return "";
        const parsed = new Date(value);
        return isNaN(parsed.getTime()) ? value : Qt.formatDateTime(parsed, "dd/MM/yyyy HH:mm");
    }
    objectName: "comexHistoryStatus"
    visible: Boolean(historyState.enabled)
    Layout.fillWidth: true
    Layout.preferredHeight: content.implicitHeight + 24
    color: Theme.surface
    radius: Theme.radius
    border.color: Theme.softLine

    ColumnLayout {
        id: content
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8
        GridLayout {
            Layout.fillWidth: true
            columns: panel.width >= 600 ? 2 : 1
            columnSpacing: 16
            rowSpacing: 8
            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 4
                Text {
                    objectName: "comexHistoryCoverage"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    textFormat: Text.PlainText
                    text: panel.covered
                        ? "Base local · " + panel.monthLabel(panel.historyState.coverageStart) + " a " + panel.monthLabel(panel.historyState.coverageEnd)
                        : "Base local · primeira carga pendente"
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    color: Theme.text
                    wrapMode: Text.WordWrap
                }
                Text {
                    objectName: "comexHistoryReference"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    textFormat: Text.PlainText
                    text: panel.covered
                        ? (panel.historyState.complete ? "Carga completa" : "Cobertura parcial")
                            + (panel.historyState.baseUpdatedAt ? " · última carga: " + panel.timeLabel(panel.historyState.baseUpdatedAt) : "")
                        : "O histórico será carregado dos períodos mais antigos aos mais recentes."
                    font.pixelSize: 11
                    color: Theme.muted
                    wrapMode: Text.WordWrap
                }
            }
            ActionButton {
                id: historyAction
                objectName: "comexHistoryAction"
                Layout.fillWidth: parent.columns === 1
                Layout.minimumWidth: naturalWidth
                implicitHeight: 34
                text: panel.historyState.busy ? "Cancelar atualização" : "Atualizar base"
                enabled: Boolean(panel.historyState.busy) || panel.pauseSeconds === 0
                onClicked: panel.historyState.busy ? panel.owner.cancel() : panel.owner.check()
                onActiveFocusChanged: if (activeFocus)
                    panel.workspace.reveal(historyAction)
                ToolTip.visible: hovered
                ToolTip.delay: 500
                ToolTip.text: (panel.historyState.busy
                    ? "Interromper a atualização e preservar a base local aceita."
                    : "Verificar a publicação do Comex Stat e atualizar o histórico quando necessário.")
                    + (panel.historyState.checkedAt ? "\nConferência da base aceita: " + panel.timeLabel(panel.historyState.checkedAt) : "")
                Accessible.name: text
                Accessible.description: panel.historyState.checkedAt
                    ? "Conferência da base aceita: " + panel.timeLabel(panel.historyState.checkedAt)
                    : "Ainda não há uma conferência de base aceita."
            }
        }
        TaskProgress {
            objectName: "comexHistoryProgress"
            visible: Boolean(panel.historyState.busy)
            Layout.fillWidth: true
            from: 0
            to: 100
            value: Number(panel.historyState.progress || 0)
            indeterminate: value === 0
            Accessible.name: "Progresso da atualização do histórico"
        }
        Text {
            objectName: "comexHistoryBackupNotice"
            Layout.fillWidth: true
            visible: text.length > 0
            text: panel.historyState.backupNotice || ""
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        Text {
            objectName: "comexHistoryMessage"
            visible: text.length > 0
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            textFormat: Text.PlainText
            text: panel.pauseSeconds > 0
                ? "Atualização em pausa por " + panel.pauseLabel + ". "
                    + (panel.covered ? "Os períodos já carregados continuam disponíveis." : "A primeira carga ainda não foi concluída.")
                : panel.historyState.error || panel.historyState.message || ""
            font.pixelSize: 11
            color: panel.historyState.error && panel.pauseSeconds === 0 ? Theme.warningText : Theme.muted
            wrapMode: Text.WordWrap
            Accessible.role: panel.historyState.error ? Accessible.AlertMessage : Accessible.StaticText
        }
    }
}
