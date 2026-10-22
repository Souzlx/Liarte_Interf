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
    readonly property real pageMargin: width < 600 ? 18 : 28
    signal moduleRequested(string key)

    function focusFirst() {
        const item = moduleCards.itemAt(0);
        if (item)
            item.forceActiveFocus();
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
                    text: "Módulos"
                    textFormat: Text.PlainText
                    color: Ui.Theme.text
                    font.pixelSize: page.width < 600 ? 25 : 30
                    font.weight: Font.DemiBold
                    font.letterSpacing: -0.5
                }
                Text {
                    Layout.fillWidth: true
                    text: "Acesse as ferramentas da LIARTE."
                    textFormat: Text.PlainText
                    color: Ui.Theme.muted
                    font.pixelSize: 14
                    wrapMode: Text.WordWrap
                }
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
