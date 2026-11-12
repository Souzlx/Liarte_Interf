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
    font.family: Ui.Theme.fontFamily
    readonly property var platformController: platform
    readonly property var viewState: controller.presentation
    readonly property bool collapsed: width < 1120
    readonly property bool draftPeriod: importsWorkspace.draftPeriod
    readonly property string activeSection: importsWorkspace.activeSection
    readonly property bool methodologyExpanded: importsWorkspace.methodologyExpanded
    readonly property bool globalModalOpen: settingsDialog.visible || importUpdatesDialog.visible || projectDialog.visible || closeDialog.visible || comexConnectionDialog.visible || comexConnectionDialog.fileChoosing
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
        if (inventory.presentation.busy) {
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
            if (window.inventoryClosing && !inventory.presentation.busy && !window.viewState.busy && !window.viewState.exportBusy && !window.viewState.metadataBusy)
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
    component NavigationButton: Ui.ActionButton {
        id: navigationButton
        property bool selected: false
        readonly property color foreground: selected ? Ui.Theme.navActiveText : Ui.Theme.sidebarText
        implicitHeight: 42
        leftPadding: 12
        rightPadding: 12
        font.pixelSize: 12
        font.weight: selected ? Font.DemiBold : Font.Medium
        contentItem: RowLayout {
            spacing: 10
            Ui.Icon {
                name: navigationButton.iconName
                color: navigationButton.foreground
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                Layout.alignment: Qt.AlignVCenter
            }
            Text {
                visible: navigationButton.text.length > 0
                Layout.fillWidth: true
                textFormat: Text.PlainText
                text: navigationButton.text
                font: navigationButton.font
                color: navigationButton.foreground
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
            }
        }
        background: Rectangle {
            radius: Ui.Theme.controlRadius
            color: navigationButton.selected ? Ui.Theme.navActive : navigationButton.hovered ? Ui.Theme.sidebarHover : "transparent"
            border.width: navigationButton.visualFocus ? 2 : 0
            border.color: Ui.Theme.navActiveText
            Behavior on color {
                enabled: Ui.Theme.motionEnabled && navigationButton.visible
                ColorAnimation {
                    duration: Ui.Theme.fast
                }
            }
        }
    }
    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            objectName: "topbar"
            Layout.fillWidth: true
            Layout.preferredHeight: Ui.Theme.topbarHeight
            color: Ui.Theme.topbar
            RowLayout {
                anchors.fill: parent
                spacing: 0
                Item {
                    Layout.preferredWidth: window.collapsed ? 64 : Ui.Theme.sidebarWidth
                    Layout.fillHeight: true
                    Ui.BrandLogo {
                        anchors.centerIn: parent
                        width: 130
                        height: width * 725 / 2167
                        visible: !window.collapsed
                    }
                    Image {
                        anchors.centerIn: parent
                        width: 30
                        height: 30
                        fillMode: Image.PreserveAspectFit
                        source: "../assets/liarte-simbolo.png"
                        visible: window.collapsed
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: window.width < 720 ? 12 : 24
                    Layout.rightMargin: window.width < 720 ? 12 : 24
                    spacing: 8
                    Text {
                        Layout.fillWidth: true
                        textFormat: Text.PlainText
                        text: platform.activeModule === "home" ? "Painel de gestão" : platform.activeTitle
                        font.pixelSize: 12
                        font.weight: Font.Medium
                        color: Ui.Theme.muted
                        elide: Text.ElideRight
                    }
                    Ui.ActionButton {
                        id: quickExportButton
                        objectName: "quickExportButton"
                        visible: platform.activeModule === "imports" && !window.viewState.demo && window.viewState.loaded
                        text: window.width >= 1000 ? (window.viewState.exportBusy ? window.viewState.exportProgress + "%" : "Exportar") : ""
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
                        objectName: "topbarHelp"
                        visible: window.width >= 900
                        text: "Ajuda"
                        iconName: "info"
                        subtle: true
                        implicitWidth: Math.max(80, naturalWidth)
                        Accessible.name: "Abrir ajuda e informações"
                        onClicked: projectDialog.open()
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
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Ui.Theme.line
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0
            Rectangle {
                id: sidebar
                objectName: "sidebar"
                Layout.fillHeight: true
                Layout.preferredWidth: window.collapsed ? 64 : Ui.Theme.sidebarWidth
                color: Ui.Theme.sidebar
                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    anchors.topMargin: 20
                    anchors.bottomMargin: 14
                    spacing: 14
                    Text {
                        visible: !window.collapsed
                        Layout.leftMargin: 10
                        text: "WORKSPACE"
                        font.pixelSize: 9
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1.5
                        color: Ui.Theme.sidebarMuted
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
                            spacing: 6
                            NavigationButton {
                                objectName: "homeNav"
                                selected: platform.activeModule === "home"
                                Layout.fillWidth: true
                                text: window.collapsed ? "" : "Visão geral"
                                iconName: "home"
                                Accessible.name: "Início"
                                font.weight: platform.activeModule === "home" ? Font.DemiBold : Font.Medium
                                onActiveFocusChanged: if (activeFocus)
                                    window.revealNavigation(this)
                                onClicked: platform.openModule("home")
                                ToolTip.visible: hovered && window.collapsed
                                ToolTip.text: "Início"
                            }
                            NavigationButton {
                                id: importsNavButton
                                objectName: "importsNav"
                                selected: platform.activeModule === "imports"
                                Layout.fillWidth: true
                                text: window.collapsed ? "" : "Importações"
                                iconName: "chart"
                                Accessible.name: "Importações"
                                font.weight: platform.activeModule === "imports" ? Font.DemiBold : Font.Medium
                                onActiveFocusChanged: if (activeFocus)
                                    window.revealNavigation(this)
                                onClicked: platform.openModule("imports")
                                ToolTip.visible: hovered && window.collapsed
                                ToolTip.text: "Importações"
                            }
                            NavigationButton {
                                objectName: "inventoryNav"
                                selected: platform.activeModule === "inventory"
                                Layout.fillWidth: true
                                text: window.collapsed ? "" : "Estoque"
                                iconName: "box"
                                Accessible.name: "Estoque"
                                font.weight: platform.activeModule === "inventory" ? Font.DemiBold : Font.Medium
                                onActiveFocusChanged: if (activeFocus)
                                    window.revealNavigation(this)
                                onClicked: platform.openModule("inventory")
                                ToolTip.visible: hovered && window.collapsed
                                ToolTip.text: "Estoque"
                            }
                            Repeater {
                                model: platform.activeModule === "inventory" && inventory.presentation.loaded ? [
                                    {
                                        key: "overview",
                                        label: "Panorama",
                                        icon: "chart"
                                    },
                                    {
                                        key: "monthly",
                                        label: "Análise mensal",
                                        icon: "chart"
                                    },
                                    {
                                        key: "products",
                                        label: "Produtos",
                                        icon: "grid"
                                    }
                                ] : []
                                NavigationButton {
                                    required property var modelData
                                    objectName: "stockJump_" + modelData.key
                                    selected: inventoryWorkspace.activeSection === modelData.key
                                    Layout.fillWidth: true
                                    implicitHeight: 36
                                    text: window.collapsed ? "" : modelData.label
                                    iconName: modelData.icon
                                    subtle: true
                                    Accessible.name: "Ir para " + modelData.label
                                    onClicked: inventoryWorkspace.navigate(modelData.key)
                                    onActiveFocusChanged: if (activeFocus)
                                        window.revealNavigation(this)
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
                                NavigationButton {
                                    required property var modelData
                                    objectName: "jump_" + modelData.key
                                    selected: window.activeSection === modelData.key
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
                                    ToolTip.visible: hovered && window.collapsed
                                    ToolTip.text: modelData.label
                                }
                            }
                        }
                    }
                    Rectangle {
                        visible: !window.collapsed && sidebar.height > 540
                        Layout.fillWidth: true
                        implicitHeight: guidance.implicitHeight + 26
                        radius: Ui.Theme.radius
                        color: Ui.Theme.sidebarHover
                        border.color: Ui.Theme.sidebarLine
                        ColumnLayout {
                            id: guidance
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 13
                            spacing: 8
                            Ui.Icon {
                                name: "info"
                                color: Ui.Theme.sidebarText
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "Central de orientação"
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                                color: Ui.Theme.navActiveText
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "Fontes, indicadores e atalhos disponíveis na ajuda."
                                font.pixelSize: 10
                                lineHeight: 1.25
                                color: Ui.Theme.sidebarText
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                    NavigationButton {
                        objectName: "projectNav"
                        Layout.fillWidth: true
                        text: window.collapsed ? "" : "Ajuda e informações"
                        iconName: "info"
                        Accessible.name: "Ajuda e informações"
                        onClicked: projectDialog.open()
                        ToolTip.visible: hovered
                        ToolTip.text: "Ajuda e informações"
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
                    inventoryState: inventory.presentation
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
        property bool showImportUpdatesOnClose: false
        onClosed: if (showImportUpdatesOnClose) {
            showImportUpdatesOnClose = false;
            Qt.callLater(() => importUpdatesDialog.open());
        }
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
                    objectName: "openImportUpdates"
                    visible: platform.activeModule === "imports" && controller.history.state.enabled
                    Layout.fillWidth: true
                    Layout.columnSpan: 2
                    text: "Atualizações de importações"
                    iconName: "refresh"
                    onClicked: {
                        settingsDialog.showImportUpdatesOnClose = true;
                        settingsDialog.close();
                    }
                }
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
                    visible: platform.activeModule === "imports" && !window.viewState.historicalMode
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
    Ui.AppDialog {
        id: importUpdatesDialog
        objectName: "importUpdatesDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(560, window.width - 40)
        modal: true
        focus: true
        title: "Atualização de importações"
        Label {
            Layout.fillWidth: true
            textFormat: Text.PlainText
            text: "Novas publicações são verificadas automaticamente."
            color: Ui.Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        Ui.ComexHistoryStatus {
            owner: controller.history
            workspace: importUpdatesDialog
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
