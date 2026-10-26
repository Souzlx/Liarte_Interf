pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: documentsPanel
    required property var workspace
    required property var backend
    objectName: "documentsPanel"
    visible: !documentsPanel.workspace.viewState.demo && documentsPanel.workspace.viewState.loaded
    Layout.fillWidth: true
    Layout.preferredHeight: exportBody.implicitHeight + 32
    color: Theme.surface
    border.color: Theme.softLine
    radius: Theme.radius
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
                color: Theme.text
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
            Item {
                Layout.fillWidth: true
            }
            ActionButton {
                objectName: "openReportFolder"
                visible: !documentsPanel.workspace.viewState.exportBusy && documentsPanel.workspace.viewState.lastExport.length > 0
                iconName: "folder"
                text: ""
                implicitWidth: 30
                implicitHeight: 28
                leftPadding: 6
                rightPadding: 6
                subtle: true
                Accessible.name: "Abrir pasta do relatório"
                ToolTip.text: "Abrir pasta · " + documentsPanel.workspace.viewState.lastExport
                onClicked: documentsPanel.backend.openExport(true)
                ToolTip.visible: hovered
                ToolTip.delay: 400
            }
        }
        GridLayout {
            Layout.fillWidth: true
            Layout.maximumWidth: 740
            columns: documentsPanel.width > 670 ? 3 : documentsPanel.width > 370 ? 2 : 1
            columnSpacing: 10
            rowSpacing: 8
            ActionButton {
                objectName: "exportExcel"
                Layout.fillWidth: true
                iconName: "file"
                text: "Baixar Excel"
                enabled: documentsPanel.workspace.viewState.canExport && !documentsPanel.workspace.draftPeriod && !documentsPanel.workspace.viewState.exportBusy
                onClicked: documentsPanel.workspace.saveDocument("excel")
                ToolTip.visible: hovered
                ToolTip.text: "Todo o período e cadastro. Os filtros da análise não reduzem a planilha."
                ToolTip.delay: 400
            }
            ActionButton {
                objectName: "exportPowerBI"
                Layout.fillWidth: true
                iconName: "chart"
                text: "Baixar Power BI"
                enabled: documentsPanel.workspace.viewState.canExport && !documentsPanel.workspace.draftPeriod && !documentsPanel.workspace.viewState.exportBusy
                onClicked: documentsPanel.workspace.saveDocument("powerbi")
                ToolTip.visible: hovered
                ToolTip.text: "Projeto Power BI e Excel do período completo, em ZIP. Extraia antes de abrir no Power BI Desktop."
                ToolTip.delay: 400
            }
            ActionButton {
                objectName: "exportPdf"
                Layout.fillWidth: true
                iconName: "download"
                text: "Baixar PDF"
                enabled: documentsPanel.workspace.viewState.canExport && !documentsPanel.workspace.draftPeriod && !documentsPanel.workspace.viewState.exportBusy && documentsPanel.workspace.viewState.appliedKind === "general" && documentsPanel.workspace.viewState.tableCount !== "0"
                onClicked: documentsPanel.workspace.saveDocument("pdf")
                ToolTip.visible: hovered
                ToolTip.text: documentsPanel.workspace.viewState.appliedKind === "municipal" ? "O PDF comercial utiliza a base geral." : "Seleção atual de toda a tabela. Acima de 1.000 kg, sem aeroportos, em A4."
                ToolTip.delay: 400
            }
        }
        Text {
            textFormat: Text.PlainText
            visible: documentsPanel.workspace.viewState.filterCount > 0 || documentsPanel.workspace.viewState.search.length > 0
            Layout.fillWidth: true
            text: "Excel e BI: período completo. PDF: seleção atual."
            color: Theme.muted
            font.pixelSize: 10
            wrapMode: Text.WordWrap
        }
        RowLayout {
            visible: documentsPanel.workspace.viewState.exportBusy
            Layout.fillWidth: true
            TaskProgress {
                objectName: "documentProgress"
                Layout.fillWidth: true
                from: 0
                to: 100
                value: documentsPanel.workspace.viewState.exportProgress
                Accessible.name: "Progresso do documento"
            }
            ActionButton {
                objectName: "cancelExport"
                iconName: "close"
                text: "Cancelar"
                implicitHeight: 32
                onClicked: documentsPanel.backend.cancelExport()
            }
        }
        Text {
            textFormat: Text.PlainText
            visible: documentsPanel.workspace.viewState.exportBusy
            Layout.fillWidth: true
            text: documentsPanel.workspace.viewState.exportStage
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        Text {
            textFormat: Text.PlainText
            visible: documentsPanel.workspace.viewState.exportError.length > 0
            Layout.fillWidth: true
            text: documentsPanel.workspace.viewState.exportError
            color: Theme.danger
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Accessible.role: Accessible.AlertMessage
        }
        Text {
            textFormat: Text.PlainText
            visible: documentsPanel.workspace.viewState.exportMessage.length > 0
            Layout.fillWidth: true
            text: documentsPanel.workspace.viewState.exportMessage
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
    }
}
