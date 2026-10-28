pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts

Rectangle {
    id: filterPanel
    required property var workspace
    required property var backend
    readonly property bool modalOpen: productFilter.popup.visible || countryFilter.popup.visible || stateFilter.popup.visible || portFilter.popup.visible || cityFilter.popup.visible
    function chooseProduct() {
        filterPanel.workspace.filtersExpanded = true;
        Qt.callLater(() => {
            filterPanel.workspace.reveal(productFilter);
            productFilter.forceActiveFocus();
            productFilter.popup.open();
        });
    }
    objectName: "filterPanel"
    visible: filterPanel.workspace.viewState.loaded
    Layout.fillWidth: true
    Layout.preferredHeight: filterBody.implicitHeight + 24
    color: Theme.surface
    radius: Theme.radius
    border.color: Theme.softLine
    ColumnLayout {
        id: filterBody
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8
        GridLayout {
            id: filterActions
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.maximumWidth: parent.width
            columns: parent.width >= toggleFilters.implicitWidth + clearFilters.implicitWidth + 2 * columnSpacing ? 3 : 1
            ActionButton {
                id: toggleFilters
                objectName: "toggleFilters"
                Layout.minimumWidth: naturalWidth
                iconName: "filter"
                text: "Filtros" + (filterPanel.workspace.viewState.filterCount ? " · " + filterPanel.workspace.viewState.filterCount : "")
                implicitHeight: 30
                subtle: true
                Accessible.name: filterPanel.workspace.filtersExpanded ? "Recolher filtros" : "Expandir filtros"
                Accessible.description: "Escolher os produtos, países e locais do recorte de importações."
                onClicked: filterPanel.workspace.filtersExpanded = !filterPanel.workspace.filtersExpanded
            }
            Item {
                visible: filterActions.columns === 3
                Layout.fillWidth: true
            }
            ActionButton {
                id: clearFilters
                objectName: "clearFilters"
                text: "Limpar"
                implicitHeight: 28
                implicitWidth: Math.max(80, naturalWidth)
                Layout.minimumWidth: implicitWidth
                subtle: true
                enabled: filterPanel.workspace.viewState.filterCount > 0 || filterPanel.workspace.viewState.search.length > 0
                onClicked: filterPanel.backend.clearFilters()
            }
        }
        GridLayout {
            Layout.fillWidth: true
            visible: filterPanel.workspace.filtersExpanded
            columns: filterPanel.width > 970 ? 4 : filterPanel.width > 550 ? 2 : 1
            columnSpacing: 12
            rowSpacing: 10
            ColumnLayout {
                Layout.fillWidth: true
                Layout.preferredWidth: 340
                spacing: 6
                Text {
                    textFormat: Text.PlainText
                    text: filterPanel.workspace.viewState.kind === "municipal" ? "Posição SH4" : "Produto / NCM"
                    color: Theme.muted
                    font.pixelSize: 11
                }
                MultiCombo {
                    id: productFilter
                    objectName: "productFilter"
                    onActiveFocusChanged: if (activeFocus)
                        filterPanel.workspace.reveal(productFilter)
                    Layout.fillWidth: true
                    model: filterPanel.backend.products
                    currentValues: filterPanel.workspace.viewState.ncmValues
                    Accessible.name: "Filtrar por produto ou código"
                    onValuesChosen: values => filterPanel.backend.setFilters("ncm", values)
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.preferredWidth: 210
                spacing: 6
                Text {
                    textFormat: Text.PlainText
                    text: "País de origem"
                    color: Theme.muted
                    font.pixelSize: 11
                }
                MultiCombo {
                    id: countryFilter
                    objectName: "countryFilter"
                    onActiveFocusChanged: if (activeFocus)
                        filterPanel.workspace.reveal(countryFilter)
                    Layout.fillWidth: true
                    model: filterPanel.backend.countries
                    currentValues: filterPanel.workspace.viewState.countryValues
                    Accessible.name: "Filtrar por país"
                    onValuesChosen: values => filterPanel.backend.setFilters("country", values)
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.preferredWidth: 115
                spacing: 6
                Text {
                    textFormat: Text.PlainText
                    text: "UF"
                    color: Theme.muted
                    font.pixelSize: 11
                }
                MultiCombo {
                    id: stateFilter
                    objectName: "stateFilter"
                    onActiveFocusChanged: if (activeFocus)
                        filterPanel.workspace.reveal(stateFilter)
                    Layout.fillWidth: true
                    model: filterPanel.backend.states
                    currentValues: filterPanel.workspace.viewState.stateValues
                    Accessible.name: "Filtrar por UF"
                    onValuesChosen: values => filterPanel.backend.setFilters("state", values)
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.preferredWidth: 245
                spacing: 6
                Text {
                    textFormat: Text.PlainText
                    text: filterPanel.workspace.viewState.kind === "municipal" ? "Município fiscal" : "Porto / URF"
                    color: Theme.muted
                    font.pixelSize: 11
                }
                MultiCombo {
                    id: portFilter
                    objectName: "portFilter"
                    visible: filterPanel.workspace.viewState.kind !== "municipal"
                    onActiveFocusChanged: if (activeFocus)
                        filterPanel.workspace.reveal(portFilter)
                    Layout.fillWidth: true
                    model: filterPanel.backend.ports
                    currentValues: filterPanel.workspace.viewState.portValues
                    Accessible.name: "Filtrar por porto ou URF"
                    onValuesChosen: values => filterPanel.backend.setFilters("port", values)
                }
                MultiCombo {
                    id: cityFilter
                    objectName: "cityFilter"
                    visible: filterPanel.workspace.viewState.kind === "municipal"
                    onActiveFocusChanged: if (activeFocus)
                        filterPanel.workspace.reveal(cityFilter)
                    Layout.fillWidth: true
                    model: filterPanel.backend.cities
                    currentValues: filterPanel.workspace.viewState.cityValues
                    Accessible.name: "Filtrar por município fiscal"
                    onValuesChosen: values => filterPanel.backend.setFilters("city", values)
                }
            }
        }
        Flow {
            visible: filterPanel.workspace.activeFilters.length > 0
            Layout.fillWidth: true
            spacing: 6
            Repeater {
                model: filterPanel.workspace.activeFilters
                FilterChip {
                    required property var modelData
                    objectName: "activeFilter_" + modelData.key
                    caption: modelData.caption
                    description: modelData.description
                    onRemoved: filterPanel.backend.setFilters(modelData.key, [])
                }
            }
        }
    }
}
