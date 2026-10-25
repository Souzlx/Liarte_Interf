import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "stockAlerts"
    property var alertData: ({})
    property var settings: ({staleDays: 90, coverageDays: 30, notice: "", error: ""})
    property bool controlsEnabled: true
    property bool current: true
    property bool busy: false
    property string activeKey: "stale"
    property bool showOccurrences: false
    property bool restoreSettingsFocus: false
    readonly property bool modalOpen: adjustmentDialog.visible
    readonly property var categories: alertData.categories || []
    readonly property var activeCategory: categories.find(category => category.key === activeKey) || categories[0] || null
    readonly property bool actionsEnabled: controlsEnabled && current && !busy
    signal thresholdsApplied(int staleDays, int coverageDays)
    signal productRequested(string code, string branch, string unit)

    implicitHeight: content.implicitHeight + 32
    radius: Theme.radius
    color: Theme.surface
    border.color: Theme.softLine

    function openSettings() {
        adjustmentDialog.open();
    }
    function restoreAdjustmentFocus() {
        if (!restoreSettingsFocus || modalOpen)
            return;
        if (!visible) {
            restoreSettingsFocus = false;
            return;
        }
        if (settingsButton.enabled) {
            restoreSettingsFocus = false;
            settingsButton.forceActiveFocus(Qt.TabFocusReason);
        }
    }
    onActionsEnabledChanged: Qt.callLater(restoreAdjustmentFocus)
    onVisibleChanged: if (!visible)
        restoreSettingsFocus = false

    ColumnLayout {
        id: content
        x: 16
        y: 16
        width: parent.width - 32
        spacing: 12

        GridLayout {
            Layout.fillWidth: true
            columns: width >= 480 ? 2 : 1
            rowSpacing: 8
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "Atenção ao estoque"
                textFormat: Text.PlainText
                color: Theme.text
                font.pixelSize: 16
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }
            ActionButton {
                id: settingsButton
                objectName: "stockAlertSettingsButton"
                Layout.fillWidth: parent.columns === 1
                Layout.minimumWidth: 0
                text: "Ajustar alertas"
                enabled: root.actionsEnabled
                Accessible.name: "Ajustar limites dos alertas de estoque"
                onClicked: root.openSettings()
            }
        }
        Text {
            objectName: "stockAlertReference"
            Layout.fillWidth: true
            visible: text.length > 0
            text: (root.alertData.asOf ? "Saldo em " + root.alertData.asOf : "") + (root.alertData.period ? " · Vendas: " + root.alertData.period : "") + " · Ocorrências por produto, filial e unidade"
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        GridLayout {
            id: categoryGrid
            objectName: "stockAlertCategories"
            Layout.fillWidth: true
            columns: width >= 720 ? 3 : 1
            columnSpacing: 10
            rowSpacing: 10
            Repeater {
                model: root.categories
                delegate: Button {
                    id: categoryButton
                    required property var modelData
                    objectName: "stockAlertCategory_" + modelData.key
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    implicitHeight: categoryContent.implicitHeight + 24
                    padding: 12
                    enabled: root.actionsEnabled
                    checked: root.activeCategory !== null && root.activeCategory.key === modelData.key
                    Accessible.name: modelData.title + ". " + (modelData.available ? modelData.count + " combinações de produto, filial e unidade." : "Avaliação indisponível.") + " Selecionar categoria."
                    onClicked: {
                        root.activeKey = modelData.key;
                        root.showOccurrences = true;
                    }
                    contentItem: ColumnLayout {
                        id: categoryContent
                        spacing: 5
                        Text {
                            Layout.fillWidth: true
                            text: categoryButton.modelData.title
                            textFormat: Text.PlainText
                            color: Theme.text
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            Layout.fillWidth: true
                            text: categoryButton.modelData.available ? String(categoryButton.modelData.count) : "—"
                            textFormat: Text.PlainText
                            color: categoryButton.checked ? Theme.accent : Theme.text
                            font.pixelSize: 23
                            font.weight: Font.DemiBold
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            Layout.fillWidth: true
                            text: categoryButton.modelData.capital || ""
                            visible: categoryButton.modelData.available && text.length > 0
                            textFormat: Text.PlainText
                            color: Theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                    }
                    background: Rectangle {
                        radius: 7
                        color: categoryButton.checked ? Theme.selected : categoryButton.hovered ? Theme.subtle : Theme.surface
                        border.color: categoryButton.visualFocus || categoryButton.checked ? Theme.accent : Theme.line
                        border.width: categoryButton.visualFocus ? 2 : 1
                    }
                }
            }
        }
        Text {
            objectName: "stockAlertUpdateNotice"
            Layout.fillWidth: true
            visible: !root.current
            text: "Os alertas exibidos correspondem à última análise concluída. Conclua a atualização para avaliar o recorte atual."
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        Text {
            objectName: "stockAlertRule"
            Layout.fillWidth: true
            visible: root.activeCategory !== null
            text: root.activeCategory ? root.activeCategory.rule || "" : ""
            textFormat: Text.PlainText
            color: Theme.text
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        Text {
            objectName: "stockAlertCategoryNotice"
            Layout.fillWidth: true
            text: root.activeCategory ? root.activeCategory.notice || "" : ""
            visible: text.length > 0
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        ActionButton {
            objectName: "stockAlertToggle"
            Layout.fillWidth: root.width < 480
            Layout.minimumWidth: 0
            text: root.showOccurrences ? "Recolher lista" : "Ver ocorrências"
            visible: root.activeCategory !== null && root.activeCategory.available && (root.activeCategory.count > 0 || root.showOccurrences)
            enabled: root.actionsEnabled
            Accessible.name: root.showOccurrences ? "Recolher ocorrências dos alertas" : "Ver ocorrências dos alertas"
            onClicked: root.showOccurrences = !root.showOccurrences
        }
        Repeater {
            model: root.showOccurrences && root.activeCategory && root.activeCategory.available ? root.activeCategory.items || [] : []
            delegate: Button {
                id: alertRow
                required property var modelData
                required property int index
                objectName: "stockAlertRow" + index
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                implicitHeight: rowContent.implicitHeight + 24
                padding: 12
                enabled: root.actionsEnabled
                Accessible.name: modelData.code + ". " + modelData.name + ". Filial " + modelData.branch + ". Unidade " + modelData.unit + ". " + (modelData.detail || "") + ". Ver posições."
                onClicked: root.productRequested(modelData.code, modelData.branch, modelData.unit)
                contentItem: ColumnLayout {
                    id: rowContent
                    spacing: 4
                    Text {
                        Layout.fillWidth: true
                        text: alertRow.modelData.code + " · " + alertRow.modelData.name
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Filial " + alertRow.modelData.branch + " · " + alertRow.modelData.unit + (alertRow.modelData.balance ? " · Saldo " + alertRow.modelData.balance : "")
                        textFormat: Text.PlainText
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        Layout.fillWidth: true
                        text: alertRow.modelData.detail || ""
                        visible: text.length > 0
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        Layout.fillWidth: true
                        text: alertRow.modelData.cost ? "Capital: " + alertRow.modelData.cost + " · Ver posições" : "Ver posições"
                        textFormat: Text.PlainText
                        color: Theme.accent
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                }
                background: Rectangle {
                    radius: 7
                    color: alertRow.hovered ? Theme.selected : Theme.subtle
                    border.color: alertRow.visualFocus ? Theme.accent : "transparent"
                    border.width: alertRow.visualFocus ? 2 : 1
                }
            }
        }
        Text {
            objectName: "stockAlertEmpty"
            Layout.fillWidth: true
            visible: root.showOccurrences && root.activeCategory !== null && root.activeCategory.available && root.activeCategory.count === 0
            text: "Nenhuma ocorrência desta regra no recorte atual."
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        Text {
            objectName: "stockAlertNotice"
            Layout.fillWidth: true
            text: root.alertData.notice || ""
            visible: root.showOccurrences && text.length > 0
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        Text {
            objectName: "stockAlertSettingsNotice"
            Layout.fillWidth: true
            text: root.settings.error || root.settings.notice || ""
            visible: text.length > 0
            textFormat: Text.PlainText
            color: root.settings.error ? Theme.danger : Theme.muted
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        Text {
            objectName: "stockAlertListNote"
            Layout.fillWidth: true
            visible: root.showOccurrences
            text: (root.activeCategory && root.activeCategory.available && root.activeCategory.count > (root.activeCategory.items || []).length ? "Exibindo " + (root.activeCategory.items || []).length + " de " + root.activeCategory.count + ". " : "") + "Contagem por produto, filial e unidade. O Excel inclui a lista completa."
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
    }

    AppDialog {
        id: adjustmentDialog
        objectName: "stockAlertSettingsDialog"
        readonly property bool validDraft: /^[0-9]+$/.test(staleDaysInput.text) && /^[0-9]+$/.test(coverageDaysInput.text) && staleDaysInput.acceptableInput && coverageDaysInput.acceptableInput
        title: "Ajustar alertas de estoque"
        closeButton: false
        onAboutToShow: {
            staleDaysInput.text = String(root.settings.staleDays);
            coverageDaysInput.text = String(root.settings.coverageDays);
        }
        onOpened: Qt.callLater(() => {
            staleDaysInput.forceActiveFocus(Qt.TabFocusReason);
            staleDaysInput.selectAll();
        })
        onClosed: {
            root.restoreSettingsFocus = true;
            Qt.callLater(root.restoreAdjustmentFocus);
        }
        Text {
            Layout.fillWidth: true
            text: "Os limites são avaliados sobre a base carregada. Não alteram seus dados nem representam uma recomendação automática de compra."
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            text: "Tempo sem venda · acima de quantos dias?"
            textFormat: Text.PlainText
            color: Theme.text
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        TextField {
            id: staleDaysInput
            objectName: "stockAlertStaleDays"
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            selectByMouse: true
            maximumLength: 4
            inputMethodHints: Qt.ImhDigitsOnly
            validator: IntValidator { bottom: 1; top: 3650 }
            Accessible.name: "Limite de dias sem venda"
            Accessible.description: "Número inteiro de 1 a 3650 dias."
        }
        Text {
            Layout.fillWidth: true
            text: "Cobertura baixa · abaixo de quantos dias?"
            textFormat: Text.PlainText
            color: Theme.text
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        TextField {
            id: coverageDaysInput
            objectName: "stockAlertCoverageDays"
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            selectByMouse: true
            maximumLength: 4
            inputMethodHints: Qt.ImhDigitsOnly
            validator: IntValidator { bottom: 1; top: 3650 }
            Accessible.name: "Limite de dias de cobertura baixa"
            Accessible.description: "Número inteiro de 1 a 3650 dias."
        }
        Text {
            Layout.fillWidth: true
            text: "Use números inteiros entre 1 e 3650, sem separadores. Produtos sem venda registrada ficam em uma categoria informativa separada."
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            visible: !root.actionsEnabled
            text: "Aguarde a análise em andamento para aplicar os limites."
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        ActionButton {
            objectName: "stockAlertDefaults"
            Layout.fillWidth: true
            text: "Restaurar padrões"
            Accessible.name: "Preencher os limites padrão: 90 dias sem venda e 30 dias de cobertura"
            onClicked: {
                staleDaysInput.text = "90";
                coverageDaysInput.text = "30";
            }
        }
        GridLayout {
            Layout.fillWidth: true
            columns: width >= 300 ? 2 : 1
            columnSpacing: 8
            rowSpacing: 8
            ActionButton {
                objectName: "stockAlertCancel"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "Cancelar"
                onClicked: adjustmentDialog.close()
            }
            ActionButton {
                objectName: "stockAlertApply"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "Aplicar limites"
                primary: true
                enabled: root.actionsEnabled && adjustmentDialog.validDraft
                onClicked: {
                    root.thresholdsApplied(Number(staleDaysInput.text), Number(coverageDaysInput.text));
                    adjustmentDialog.close();
                }
            }
        }
    }
}
