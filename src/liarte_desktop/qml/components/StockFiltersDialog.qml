pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts

AppDialog {
    id: dialog
    objectName: "stockFiltersDialog"
    required property var stockController
    property bool controlsEnabled: true
    property var draft: ({})
    readonly property var state: stockController.presentation || ({})
    readonly property var options: stockController.filterOptions || []
    readonly property var fieldKeys: ["start", "end", "unit", "branch", "warehouse", "group", "kind", "abc", "activity", "balance"]
    readonly property var fields: fieldKeys.map(key => options.find(option => option.key === key)).filter(Boolean)
    readonly property bool validPeriod: Boolean(draft.start && draft.end && draft.start <= draft.end)
    readonly property string error: stockController.filterState.error || ""
    title: "Refinar recorte de estoque"
    width: Math.min(760, parent ? parent.width - 32 : 760)
    height: Math.min(implicitHeight, 730, parent ? parent.height - 32 : 730)
    closeButton: false

    function syncDraft() {
        draft = Object.assign({}, state.selection || {});
        stockController.clearFilterError();
    }
    function setChoice(key, value) {
        const next = Object.assign({}, draft);
        next[key] = value;
        draft = next;
    }
    function clearOptions() {
        const next = Object.assign({}, draft);
        for (const field of fields)
            if (field.key !== "start" && field.key !== "end")
                next[field.key] = "";
        draft = next;
        stockController.clearFilterError();
    }
    function apply() {
        if (controlsEnabled && validPeriod && stockController.applyFilters(draft)) {
            applied();
            close();
        }
    }
    onAboutToShow: syncDraft()
    Connections {
        target: dialog.stockController
        function onOptionsChanged() {
            if (dialog.visible)
                dialog.close();
        }
    }

    Column {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        spacing: 16
        Text {
            width: parent.width
            text: "Escolha o recorte e aplique todas as opções de uma vez. Fechar ou cancelar preserva o recorte anterior. A busca de produto permanece disponível na página."
            color: Theme.muted
            textFormat: Text.PlainText
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        GridLayout {
            width: parent.width
            columns: width >= 520 ? 2 : 1
            columnSpacing: 14
            rowSpacing: 12
            Repeater {
                model: dialog.fields
                ColumnLayout {
                    id: field
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 5
                    Text {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: field.modelData.key === "start" ? "Histórico · mês inicial" : field.modelData.key === "end" ? "Histórico · mês final" : field.modelData.label
                        textFormat: Text.PlainText
                        color: Theme.muted
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                    }
                    AppCombo {
                        objectName: "stockDraft_" + field.modelData.key
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        model: field.modelData.values
                        currentIndex: Math.max(0, model.findIndex(option => option.value === (dialog.draft[field.modelData.key] || "")))
                        enabled: dialog.controlsEnabled
                        Accessible.name: field.modelData.label + " do recorte de estoque"
                        onActivated: index => dialog.setChoice(field.modelData.key, model[index].value)
                    }
                }
            }
        }
        Text {
            objectName: "stockFiltersPeriodNotice"
            width: parent.width
            visible: !dialog.validPeriod
            text: "O mês inicial deve ser anterior ou igual ao mês final."
            textFormat: Text.PlainText
            color: Theme.danger
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        Text {
            width: parent.width
            text: "O período filtra vendas e fechamentos históricos; os saldos atuais continuam na data da base. ABC, última venda e sinal do saldo usam a situação atual para selecionar produtos."
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        Text {
            objectName: "stockFiltersWarehouseNotice"
            width: parent.width
            visible: Boolean(dialog.draft.warehouse)
            text: "As vendas são registradas por filial. Com filtro de armazém, comparações de vendas e cobertura que exigem essa alocação ficam indisponíveis."
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        Text {
            objectName: "stockFiltersError"
            width: parent.width
            visible: text.length > 0
            text: dialog.error
            textFormat: Text.PlainText
            color: Theme.danger
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        GridLayout {
            width: parent.width
            columns: width >= 560 ? 3 : 1
            columnSpacing: 10
            rowSpacing: 8
            ActionButton {
                objectName: "stockFiltersClear"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "Limpar opções"
                subtle: true
                enabled: dialog.controlsEnabled
                onClicked: dialog.clearOptions()
            }
            ActionButton {
                objectName: "stockFiltersCancel"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "Cancelar"
                onClicked: dialog.close()
            }
            ActionButton {
                objectName: "stockFiltersApply"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "Aplicar recorte"
                primary: true
                enabled: dialog.controlsEnabled && dialog.validPeriod
                onClicked: dialog.apply()
            }
        }
    }
}
