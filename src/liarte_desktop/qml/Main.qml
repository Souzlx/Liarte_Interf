import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components" as Ui

ApplicationWindow {
    id: window
    objectName: "mainWindow"
    width: 1380
    height: 900
    minimumWidth: 500
    minimumHeight: 400
    visible: false
    title: platform.windowTitle
    color: Ui.Theme.canvas
    readonly property var platformController: platform
    readonly property var viewState: controller.presentation
    readonly property bool collapsed: width < 1120
    readonly property bool draftPeriod: importsWorkspace.draftPeriod
    readonly property string activeSection: importsWorkspace.activeSection
    readonly property bool methodologyExpanded: importsWorkspace.methodologyExpanded
    readonly property bool globalModalOpen: settingsDialog.visible || projectDialog.visible || closeDialog.visible || comexConnectionDialog.visible || comexConnectionDialog.fileChoosing
    property bool inventoryClosing: false
    readonly property bool modalOpen: globalModalOpen || importsWorkspace.modalOpen || inventoryWorkspace.modalOpen

    function revealNavigation(item) {
        Qt.callLater(() => {
            if (!item || !item.visible)
                return;
            const viewport = moduleNavigation.contentItem;
            const top = item.mapToItem(navigationColumn, 0, 0).y;
            const maximum = Math.max(0, moduleNavigation.contentHeight - moduleNavigation.availableHeight);
            if (top < viewport.contentY)
                viewport.contentY = Math.max(0, top);
            else if (top + item.height > viewport.contentY + moduleNavigation.availableHeight)
                viewport.contentY = Math.min(maximum, top + item.height - moduleNavigation.availableHeight);
        });
    }
    function navigate(section) {
        platform.openModule("imports");
        importsWorkspace.navigate(section);
    }
    function chooseProduct() {
        platform.openModule("imports");
        importsWorkspace.chooseProduct();
    }
    Binding {
        target: Ui.Theme
        property: "dark"
        value: preferences.state.dark
    }
    Binding {
        target: Ui.Theme
        property: "reducedMotion"
        value: preferences.state.reducedMotion
    }
    Binding {
        target: Ui.Theme
        property: "windowVisible"
        value: window.visible && window.visibility !== Window.Minimized
    }
    palette.window: Ui.Theme.surface
    palette.windowText: Ui.Theme.text
    palette.text: Ui.Theme.text
    palette.buttonText: Ui.Theme.text
    palette.base: Ui.Theme.surface
    palette.highlight: Ui.Theme.selected
    palette.highlightedText: Ui.Theme.text

    onClosing: event => {
        if (inventory.state.busy) {
            event.accepted = false;
            if (!inventoryClosing)
                closeDialog.open();
        } else if (viewState.busy || viewState.exportBusy || viewState.metadataBusy) {
            event.accepted = false;
            if (!viewState.closing) {
                if (viewState.busy || viewState.exportBusy)
                    closeDialog.open();
                else
                    controller.requestClose();
            }
        }
    }
    Connections {
        target: controller
        function onReadyToClose() {
            window.close();
        }
    }
    Connections {
        target: platform
        function onNavigationChanged() {
            pageTransition.stop();
            routeStack.opacity = 1;
            if (Ui.Theme.motionEnabled)
                pageTransition.restart();
            Qt.callLater(() => {
                if (platform.activeModule === "imports") {
                    if (window.viewState.loaded)
                        importsNavButton.forceActiveFocus();
                    else
                        importsWorkspace.restoreFocus();
                } else if (platform.activeModule === "inventory") {
                    inventory.ensureLoaded();
                    inventoryWorkspace.restoreFocus();
                } else
                    homePage.focusFirst();
            });
        }
    }
    Connections {
        target: inventory
        function onChanged() {
            if (window.inventoryClosing && !inventory.state.busy && !window.viewState.busy && !window.viewState.exportBusy && !window.viewState.metadataBusy)
                Qt.callLater(() => window.close());
        }
    }
    Connections {
        target: Ui.Theme
        function onMotionEnabledChanged() {
            if (!Ui.Theme.motionEnabled) {
                pageTransition.stop();
                routeStack.opacity = 1;
            }
        }
    }
    NumberAnimation {
        id: pageTransition
        objectName: "moduleTransition"
        target: routeStack
        property: "opacity"
        from: 0.94
        to: 1
        duration: 140
        easing.type: Easing.OutCubic
    }
    Shortcut {
        sequence: "Ctrl+Q"
        onActivated: (window.viewState.busy || window.viewState.exportBusy) ? closeDialog.open() : window.close()
    }
    Shortcut {
        sequence: "Ctrl+1"
        enabled: !window.modalOpen
        onActivated: platform.openModule("home")
    }
    Shortcut {
        sequence: "Ctrl+2"
        enabled: !window.modalOpen
        onActivated: platform.openModule("imports")
    }
    Shortcut {
        sequence: "Ctrl+3"
        enabled: !window.modalOpen
        onActivated: platform.openModule("inventory")
    }
    RowLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            id: sidebar
            objectName: "sidebar"
            Layout.fillHeight: true
            Layout.preferredWidth: window.collapsed ? 64 : 190
            color: Ui.Theme.surface
            Rectangle {
                anchors.right: parent.right
                width: 1
                height: parent.height
                color: Ui.Theme.line
            }
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: window.collapsed ? 10 : 18
                spacing: 8
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: window.collapsed ? 82 : 96
                    Ui.BrandLogo {
                        width: 146
                        height: width * 725 / 2167
                        anchors.top: parent.top
                        anchors.topMargin: 19
                        visible: !window.collapsed
                    }
                    Image {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 17
                        width: 32
                        height: 32
                        fillMode: Image.PreserveAspectFit
                        source: "../assets/liarte-simbolo.png"
                        visible: window.collapsed
                    }
                }
                ScrollView {
                    id: moduleNavigation
                    objectName: "moduleNavigation"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 0
                    clip: true
                    contentWidth: availableWidth
                    contentHeight: navigationColumn.implicitHeight
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded
                    ColumnLayout {
                        id: navigationColumn
                        width: moduleNavigation.availableWidth
                        spacing: 8
                        Ui.ActionButton {
                            objectName: "homeNav"
                            Layout.fillWidth: true
                            text: window.collapsed ? "" : "Início"
                            iconName: "home"
                            Accessible.name: "Início"
                            font.weight: platform.activeModule === "home" ? Font.DemiBold : Font.Medium
                            onActiveFocusChanged: if (activeFocus)
                                window.revealNavigation(this)
                            onClicked: platform.openModule("home")
                            background: Rectangle {
                                radius: 7
                                color: platform.activeModule === "home" ? Ui.Theme.selected : parent.hovered ? Ui.Theme.hover : "transparent"
                                border.color: parent.visualFocus ? Ui.Theme.accent : "transparent"
                                border.width: 2
                            }
                            ToolTip.visible: hovered && window.collapsed
                            ToolTip.text: "Início"
                        }
                        Ui.ActionButton {
                            id: importsNavButton
                            objectName: "importsNav"
                            Layout.fillWidth: true
                            text: window.collapsed ? "" : "Importações"
                            iconName: "chart"
                            Accessible.name: "Importações"
                            font.weight: platform.activeModule === "imports" ? Font.DemiBold : Font.Medium
                            background: Rectangle {
                                radius: 7
                                color: platform.activeModule === "imports" ? Ui.Theme.selected : parent.hovered ? Ui.Theme.hover : "transparent"
                                border.color: parent.visualFocus ? Ui.Theme.accent : "transparent"
                                border.width: 2
                            }
                            onActiveFocusChanged: if (activeFocus)
                                window.revealNavigation(this)
                            onClicked: platform.openModule("imports")
                            ToolTip.visible: hovered && window.collapsed
                            ToolTip.text: "Importações"
                        }
                        Ui.ActionButton {
                            objectName: "inventoryNav"
                            Layout.fillWidth: true
                            text: window.collapsed ? "" : "Estoque"
                            iconName: "box"
                            Accessible.name: "Estoque"
                            font.weight: platform.activeModule === "inventory" ? Font.DemiBold : Font.Medium
                            onActiveFocusChanged: if (activeFocus)
                                window.revealNavigation(this)
                            onClicked: platform.openModule("inventory")
                            background: Rectangle {
                                radius: 7
                                color: platform.activeModule === "inventory" ? Ui.Theme.selected : parent.hovered ? Ui.Theme.hover : "transparent"
                                border.color: parent.visualFocus ? Ui.Theme.accent : "transparent"
                                border.width: 2
                            }
                            ToolTip.visible: hovered && window.collapsed
                            ToolTip.text: "Estoque"
                        }
                        Repeater {
                            model: platform.activeModule === "inventory" && inventory.state.loaded ? [
                                {
                                    key: "overview",
                                    label: "Panorama",
                                    icon: "chart"
                                },
                                {
                                    key: "products",
                                    label: "Produtos",
                                    icon: "grid"
                                }
                            ] : []
                            Ui.ActionButton {
                                required property var modelData
                                objectName: "stockJump_" + modelData.key
                                Layout.fillWidth: true
                                implicitHeight: 36
                                text: window.collapsed ? "" : modelData.label
                                iconName: modelData.icon
                                subtle: true
                                Accessible.name: "Ir para " + modelData.label
                                onClicked: inventoryWorkspace.navigate(modelData.key)
                                onActiveFocusChanged: if (activeFocus)
                                    window.revealNavigation(this)
                                background: Rectangle {
                                    radius: 6
                                    color: inventoryWorkspace.activeSection === parent.modelData.key ? Ui.Theme.selected : parent.hovered ? Ui.Theme.hover : "transparent"
                                    border.color: parent.visualFocus ? Ui.Theme.accent : "transparent"
                                }
                                ToolTip.visible: hovered && window.collapsed
                                ToolTip.text: modelData.label
                            }
                        }
                        Repeater {
                            model: platform.activeModule === "imports" && window.viewState.loaded ? [
                                {
                                    key: "summary",
                                    label: "Resumo",
                                    icon: "chart"
                                },
                                {
                                    key: "buying",
                                    label: "Compras",
                                    icon: "price"
                                },
                                {
                                    key: "records",
                                    label: "Registros",
                                    icon: "grid"
                                }
                            ] : []
                            Ui.ActionButton {
                                required property var modelData
                                objectName: "jump_" + modelData.key
                                Layout.fillWidth: true
                                implicitHeight: 36
                                text: window.collapsed ? "" : modelData.label
                                iconName: modelData.icon
                                subtle: true
                                Accessible.name: "Ir para " + modelData.label
                                onActiveFocusChanged: if (activeFocus)
                                    window.revealNavigation(this)
                                onClicked: window.navigate(modelData.key)
                                Accessible.description: window.activeSection === modelData.key ? "Seção atual" : ""
                                background: Rectangle {
                                    radius: 6
                                    color: window.activeSection === parent.modelData.key ? Ui.Theme.selected : parent.hovered ? Ui.Theme.hover : "transparent"
                                    border.color: parent.visualFocus ? Ui.Theme.accent : "transparent"
                                    border.width: 2
                                    Rectangle {
                                        visible: window.activeSection === parent.parent.modelData.key
                                        width: 3
                                        height: parent.height - 16
                                        anchors.left: parent.left
                                        anchors.verticalCenter: parent.verticalCenter
                                        radius: 1
                                        color: Ui.Theme.accent
                                    }
                                }
                                ToolTip.visible: hovered && window.collapsed
                                ToolTip.text: modelData.label
                            }
                        }
                    }
                }
                Ui.ActionButton {
                    objectName: "projectNav"
                    Layout.fillWidth: true
                    subtle: true
                    text: window.collapsed ? "" : "Ajuda"
                    iconName: "info"
                    Accessible.name: "Ajuda e informações"
                    onClicked: projectDialog.open()
                    ToolTip.visible: hovered
                    ToolTip.text: "Ajuda e informações"
                }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 64
                color: Ui.Theme.surface
                Rectangle {
                    y: parent.height - 1
                    width: parent.width
                    height: 1
                    color: Ui.Theme.line
                }
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: window.width < 720 ? 18 : 28
                    anchors.rightMargin: window.width < 720 ? 18 : 28
                    spacing: 10
                    Text {
                        textFormat: Text.PlainText
                        text: platform.activeTitle
                        font.pixelSize: window.width < 720 ? 21 : 24
                        font.weight: Font.DemiBold
                        font.letterSpacing: -0.4
                        color: Ui.Theme.text
                    }
                    Item {
                        Layout.fillWidth: true
                    }
                    Ui.ActionButton {
                        id: quickExportButton
                        objectName: "quickExportButton"
                        visible: platform.activeModule === "imports" && !window.viewState.demo && window.viewState.loaded
                        text: window.width >= 1000 ? (window.viewState.exportBusy ? window.viewState.exportProgress + "%" : "Baixar") : ""
                        iconName: window.viewState.exportBusy ? "file" : "download"
                        implicitWidth: window.width >= 1000 ? Math.max(108, naturalWidth) : 40
                        Layout.minimumWidth: implicitWidth
                        leftPadding: window.width >= 1000 ? 14 : 10
                        rightPadding: leftPadding
                        primary: true
                        enabled: window.viewState.exportBusy || (window.viewState.canExport && !window.draftPeriod)
                        Accessible.name: window.viewState.exportBusy ? "Acompanhar geração do documento" : "Baixar documentos"
                        onClicked: window.viewState.exportBusy ? window.navigate("documents") : importsWorkspace.openExportMenu()
                        ToolTip.visible: hovered
                        ToolTip.text: window.viewState.exportBusy ? "Documento em preparação. Acompanhar ou cancelar." : "Baixar Excel, Power BI ou PDF"
                        ToolTip.delay: 400
                    }
                    Ui.ActionButton {
                        objectName: "themeButton"
                        iconName: window.viewState.dark ? "sun" : "moon"
                        text: ""
                        subtle: true
                        implicitWidth: 40
                        leftPadding: 10
                        rightPadding: 10
                        Accessible.name: window.viewState.dark ? "Ativar modo claro" : "Ativar modo escuro"
                        onClicked: preferences.setPreference("dark", !preferences.state.dark)
                        ToolTip.visible: hovered
                        ToolTip.text: Accessible.name
                        ToolTip.delay: 400
                    }
                    Ui.ActionButton {
                        objectName: "settingsButton"
                        iconName: "settings"
                        text: window.width < 680 ? "" : "Preferências"
                        implicitWidth: window.width < 680 ? 40 : Math.max(150, naturalWidth)
                        Layout.minimumWidth: implicitWidth
                        leftPadding: window.width < 680 ? 10 : 14
                        rightPadding: leftPadding
                        Accessible.name: "Preferências"
                        onClicked: settingsDialog.open()
                        ToolTip.visible: hovered && window.width < 680
                        ToolTip.text: "Preferências"
                        ToolTip.delay: 400
                    }
                }
            }
            StackLayout {
                id: routeStack
                objectName: "moduleStack"
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: platform.activeModule === "home" ? 0 : platform.activeModule === "imports" ? 1 : 2
                HomePage {
                    id: homePage
                    platform: window.platformController
                    importState: window.viewState
                    inventoryState: inventory.state
                    importAnalysis: controller.analysis
                    inventoryAnalysis: inventory.analysis
                    onModuleRequested: key => platform.openModule(key)
                }
                ImportsWorkspace {
                    id: importsWorkspace
                    hostWindow: window
                    exportAnchor: quickExportButton
                    globalModalOpen: window.globalModalOpen
                }
                InventoryWorkspace {
                    id: inventoryWorkspace
                    hostWindow: window
                    Component.onCompleted: if (platform.activeModule === "inventory")
                        inventory.ensureLoaded()
                }
            }
        }
    }
    Ui.AppDialog {
        id: settingsDialog
        objectName: "settingsDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(460, window.width - 40)
        modal: true
        title: "Preferências"
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 12
            Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                visible: preferences.notice.length > 0
                text: preferences.notice
                wrapMode: Text.WordWrap
                color: Ui.Theme.danger
                font.pixelSize: 11
            }
            Label {
                text: "Ao abrir o sistema"
                textFormat: Text.PlainText
                color: Ui.Theme.muted
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }
            Ui.AppCombo {
                objectName: "startupPagePreference"
                Layout.fillWidth: true
                model: platform.startupOptions
                currentIndex: model.findIndex(option => option.value === platform.startupPage)
                Accessible.name: "Tela inicial do sistema"
                onActivated: platform.setStartupPage(currentValue)
            }
            Label {
                textFormat: Text.PlainText
                text: "Aparência"
                color: Ui.Theme.muted
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }
            Ui.AppCheck {
                objectName: "darkPreference"
                text: "Modo escuro"
                checked: preferences.state.dark
                onToggled: preferences.setPreference("dark", checked)
            }
            Ui.AppCheck {
                objectName: "motionPreference"
                text: "Reduzir animações"
                checked: preferences.state.reducedMotion
                onToggled: preferences.setPreference("reducedMotion", checked)
            }
            Ui.AppCheck {
                objectName: "compactPreference"
                text: "Tabela compacta"
                checked: preferences.state.compact
                onToggled: preferences.setPreference("compact", checked)
            }
            Rectangle {
                visible: platform.activeModule === "imports"
                Layout.fillWidth: true
                height: 1
                color: Ui.Theme.line
            }
            Label {
                visible: platform.activeModule === "imports"
                textFormat: Text.PlainText
                text: "Documentos"
                color: Ui.Theme.muted
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }
            Ui.AppCheck {
                objectName: "monthlySheets"
                visible: platform.activeModule === "imports"
                text: "Criar abas mensais no Excel"
                checked: window.viewState.monthlySheets
                onToggled: controller.setExportOption("monthlySheets", checked)
            }
            Rectangle {
                visible: platform.activeModule === "imports" && !window.viewState.demo
                Layout.fillWidth: true
                height: 1
                color: Ui.Theme.line
            }
            Label {
                visible: platform.activeModule === "imports" && !window.viewState.demo
                textFormat: Text.PlainText
                text: "Consulta"
                color: Ui.Theme.muted
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }
            GridLayout {
                Layout.fillWidth: true
                columns: 2
                Ui.ActionButton {
                    objectName: "configureComexAccess"
                    visible: platform.activeModule === "imports" && comexAccess.state.available
                    Layout.fillWidth: true
                    Layout.columnSpan: 2
                    text: "Acesso ao Comex Stat"
                    iconName: "settings"
                    onClicked: {
                        settingsDialog.close();
                        comexConnectionDialog.open();
                    }
                }
                Ui.ActionButton {
                    objectName: "refreshAvailability"
                    visible: platform.activeModule === "imports"
                    Layout.fillWidth: true
                    text: "Verificar fonte"
                    iconName: "refresh"
                    enabled: !window.viewState.demo && !window.viewState.busy && !window.viewState.metadataBusy
                    onClicked: controller.refreshAvailability()
                }
                Ui.ActionButton {
                    objectName: "openDiagnostics"
                    Layout.fillWidth: true
                    text: "Diagnóstico"
                    iconName: "folder"
                    onClicked: controller.openDiagnostics()
                }
            }
        }
    }
    Ui.ComexConnectionDialog {
        id: comexConnectionDialog
    }
    Ui.AppDialog {
        id: projectDialog
        objectName: "projectDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(510, window.width - 40)
        modal: true
        title: "Ajuda"
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 14
            Label {
                textFormat: Text.PlainText
                text: platform.activeModule === "imports" ? "Importações" : platform.activeModule === "inventory" ? "Estoque" : "Liarte"
                font.bold: true
                color: Ui.Theme.text
            }
            Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: platform.activeModule === "imports" ? "Escolha o período e consulte. Use os filtros para atualizar indicadores e gráficos; a busca livre restringe somente a tabela. Clique em um filtro ativo para removê-lo." : platform.activeModule === "inventory" ? "Abra o PBIX com dados ou uma base .liarte. Use os filtros para atualizar toda a análise. Selecione uma posição e clique em Detalhar produto para ver vendas, cobertura e giro. Baixar Excel exporta o recorte atual. Use o ícone de informações do módulo para conferir os critérios de cálculo." : "Em Início, escolha um módulo. Voltar para Início mantém sua consulta aberta. Em Preferências, você pode escolher a tela inicial, o tema e as animações."
                wrapMode: Text.WordWrap
                color: Ui.Theme.text
            }
            Label {
                visible: platform.activeModule === "imports"
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: "Excel e Power BI incluem o período completo. PDF usa os filtros e a busca, com nomes comerciais, acima de 1.000 kg e sem aeroportos. O ZIP do BI deve ser extraído e aberto no Power BI Desktop."
                wrapMode: Text.WordWrap
                color: Ui.Theme.text
            }
            Label {
                visible: platform.activeModule === "imports"
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: "Fonte: Comex Stat / MDIC. Registros mensais agregados, sem pedidos ou empresas identificadas. A base geral é NCM/CIF; municípios são domicílio fiscal, SH4/FOB e abrangem mais produtos. Não some os totais das duas bases."
                wrapMode: Text.WordWrap
                color: Ui.Theme.muted
                font.pixelSize: 11
            }
            Label {
                visible: platform.activeModule === "imports"
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: window.viewState.sourceStatus + (window.viewState.sourceUpdated ? " · Atualizado em " + window.viewState.sourceUpdated.split("-").reverse().join("/") : "")
                wrapMode: Text.WordWrap
                color: Ui.Theme.muted
                font.pixelSize: 11
            }
            Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: "Ctrl+1 · Início     Ctrl+2 · Importações     Ctrl+3 · Estoque\n" + (platform.activeModule === "imports" ? "Ctrl+F · Buscar     F5 · Consultar     " : "") + "Ctrl+Q · Sair"
                wrapMode: Text.WordWrap
                color: Ui.Theme.muted
                font.pixelSize: 11
            }
            Label {
                textFormat: Text.PlainText
                text: "LIARTE Metalquímica · " + appVersion
                color: Ui.Theme.muted
                font.pixelSize: 10
            }
        }
    }
    Ui.AppDialog {
        id: closeDialog
        objectName: "closeDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(450, window.width - 40)
        modal: true
        title: "Encerrar o sistema?"
        closeButton: false
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 15
            Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: "Há uma tarefa em andamento. Você pode continuar ou cancelá-la antes de sair. Uma resposta da rede pode levar alguns segundos para encerrar."
                wrapMode: Text.WordWrap
                color: Ui.Theme.text
            }
            RowLayout {
                Ui.ActionButton {
                    text: "Continuar"
                    onClicked: closeDialog.close()
                }
                Ui.ActionButton {
                    objectName: "confirmClose"
                    text: "Cancelar e sair"
                    primary: true
                    onClicked: {
                        closeDialog.close();
                        window.inventoryClosing = true;
                        inventory.cancel();
                        controller.requestClose();
                        window.close();
                    }
                }
            }
        }
    }
}
