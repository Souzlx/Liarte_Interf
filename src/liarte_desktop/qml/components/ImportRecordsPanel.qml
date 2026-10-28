pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: recordsPanel
    required property var workspace
    required property var backend
    required property var tableModel
    readonly property var tableControl: tableView
    readonly property var searchControl: searchBox
    readonly property bool modalOpen: tableProfile.popup.visible
    signal detailsRequested
    function focusFirst() {
        tableView.forceActiveFocus(Qt.TabFocusReason);
        recordsPanel.workspace.reveal(tableView);
    }
    function focusSearch() {
        recordsPanel.workspace.reveal(searchBox);
        searchBox.forceActiveFocus(Qt.ShortcutFocusReason);
        searchBox.selectAll();
    }
    function resetPosition() {
        tableView.contentX = 0;
        tableView.contentY = 0;
    }
    NumberAnimation {
        id: recordsTransition
        objectName: "recordsTransition"
        target: tableView
        property: "opacity"
        from: 0.90
        to: 1
        duration: 140
        easing.type: Easing.OutCubic
    }
    Connections {
        target: recordsPanel.tableModel
        function onContentChanged() {
            if (Theme.motionEnabled && tableView.visible && recordsPanel.workspace.viewState.loaded)
                recordsTransition.restart();
            else {
                recordsTransition.stop();
                tableView.opacity = 1;
            }
        }
    }
    Connections {
        target: Theme
        function onMotionEnabledChanged() {
            if (!Theme.motionEnabled) {
                recordsTransition.stop();
                tableView.opacity = 1;
            }
        }
    }
    objectName: "recordsPanel"
    visible: recordsPanel.workspace.viewState.loaded
    Layout.fillWidth: true
    Layout.preferredHeight: tableBody.implicitHeight + 34
    color: Theme.surface
    radius: Theme.radius
    border.color: Theme.softLine
    ColumnLayout {
        id: tableBody
        anchors {
            fill: parent
            margins: 17
        }
        spacing: 10
        GridLayout {
            Layout.fillWidth: true
            columns: recordsPanel.width > 970 ? 3 : recordsPanel.width > 550 ? 2 : 1
            columnSpacing: 12
            rowSpacing: 10
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Text {
                    textFormat: Text.PlainText
                    text: "Registros"
                    color: Theme.text
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                }
                Text {
                    textFormat: Text.PlainText
                    text: recordsPanel.workspace.viewState.tableRange
                    color: Theme.muted
                    font.pixelSize: 10
                }
            }
            AppCombo {
                id: tableProfile
                objectName: "tableProfile"
                Layout.preferredWidth: 180
                implicitHeight: 36
                model: [
                    {
                        label: "Visão de compras",
                        value: "buying"
                    },
                    {
                        label: "Todas as colunas",
                        value: "full"
                    }
                ]
                Accessible.name: "Colunas da tabela"
                onCurrentValueChanged: {
                    recordsPanel.tableModel.setProfile(currentValue);
                    Qt.callLater(() => {
                        tableView.contentX = 0;
                        tableView.forceLayout();
                    });
                }
                Component.onCompleted: recordsPanel.tableModel.setProfile(currentValue)
            }
            TextField {
                id: searchBox
                objectName: "searchBox"
                Layout.fillWidth: true
                Layout.columnSpan: parent.columns === 2 ? 2 : 1
                Layout.preferredWidth: 360
                Layout.maximumWidth: 400
                Layout.alignment: Qt.AlignRight
                implicitHeight: 39
                text: recordsPanel.workspace.viewState.search
                placeholderText: "Buscar na tabela…"
                maximumLength: 250
                rightPadding: 38
                ActionButton {
                    objectName: "clearSearch"
                    visible: searchBox.text.length > 0
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.rightMargin: 3
                    implicitWidth: 30
                    implicitHeight: 30
                    leftPadding: 6
                    rightPadding: 6
                    subtle: true
                    text: ""
                    iconName: "close"
                    Accessible.name: "Limpar busca da tabela"
                    onClicked: recordsPanel.backend.setFilter("search", "")
                }
                color: Theme.text
                placeholderTextColor: Theme.muted
                font.pixelSize: 12
                leftPadding: 11
                Accessible.name: "Buscar somente na tabela, sem alterar indicadores e gráficos"
                onTextEdited: recordsPanel.backend.setFilter("search", text)
                background: Rectangle {
                    radius: 5
                    color: Theme.surface
                    border.color: parent.activeFocus ? Theme.accent : Theme.line
                    border.width: parent.activeFocus ? 2 : 1
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 385
            objectName: "recordsViewport"
            clip: true
            border.color: Theme.line
            color: Theme.surface
            HorizontalHeaderView {
                id: tableHeader
                anchors {
                    top: parent.top
                    left: parent.left
                    right: parent.right
                }
                height: 42
                syncView: tableView
                clip: true
                delegate: Rectangle {
                    id: headerCell
                    required property int column
                    required property string display
                    objectName: "tableHeader" + column
                    clip: true
                    implicitWidth: tableView.columnWidthProvider(column)
                    implicitHeight: 42
                    color: Theme.subtle
                    Text {
                        textFormat: Text.PlainText
                        anchors {
                            fill: parent
                            leftMargin: 11
                            rightMargin: 11
                        }
                        verticalAlignment: Text.AlignVCenter
                        text: headerCell.display + (recordsPanel.workspace.viewState.sortColumn === tableView.sourceColumn(headerCell.column) ? recordsPanel.workspace.viewState.descending ? " ↓" : " ↑" : "")
                        horizontalAlignment: tableView.numericColumn(headerCell.column) ? Text.AlignRight : Text.AlignLeft
                        color: Theme.text
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    TapHandler {
                        onTapped: recordsPanel.backend.sortByColumn(tableView.sourceColumn(headerCell.column))
                    }
                    Accessible.role: Accessible.ColumnHeader
                    Accessible.name: "Ordenar por " + display
                    Accessible.onPressAction: recordsPanel.backend.sortByColumn(tableView.sourceColumn(headerCell.column))
                }
            }
            TableView {
                id: tableView
                objectName: "recordsTable"
                onVisibleChanged: {
                    if (!visible) {
                        recordsTransition.stop();
                        opacity = 1;
                    }
                }
                anchors {
                    top: tableHeader.bottom
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }
                clip: true
                model: recordsPanel.tableModel
                reuseItems: true
                boundsBehavior: Flickable.StopAtBounds
                columnSpacing: 1
                rowSpacing: 1
                property var columnSpecs: recordsPanel.tableModel.viewColumns
                function sourceColumn(column) {
                    return columnSpecs[column] ? columnSpecs[column].source : -1;
                }
                function numericColumn(column) {
                    return columnSpecs[column] ? columnSpecs[column].numeric : false;
                }
                onColumnSpecsChanged: forceLayout()
                property bool compactMode: recordsPanel.workspace.viewState.compact
                columnWidthProvider: column => columnSpecs[column] ? columnSpecs[column].width : 120
                rowHeightProvider: row => compactMode ? 32 : 40
                onCompactModeChanged: forceLayout()
                onWidthChanged: forceLayout()
                ScrollBar.horizontal: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }
                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }
                Keys.onPressed: event => {
                    let count = recordsPanel.tableModel.rowCount();
                    if (event.key === Qt.Key_Down && count) {
                        const row = Math.min(count - 1, recordsPanel.workspace.viewState.selection + 1);
                        recordsPanel.backend.selectRow(row);
                        positionViewAtRow(row, TableView.Contain);
                        event.accepted = true;
                    } else if (event.key === Qt.Key_Up && count) {
                        const row = Math.max(0, recordsPanel.workspace.viewState.selection - 1);
                        recordsPanel.backend.selectRow(row);
                        positionViewAtRow(row, TableView.Contain);
                        event.accepted = true;
                    } else if (count && [Qt.Key_Home, Qt.Key_End, Qt.Key_PageDown, Qt.Key_PageUp].includes(event.key)) {
                        const step = event.key === Qt.Key_PageDown ? 8 : -8;
                        const row = event.key === Qt.Key_Home ? 0 : event.key === Qt.Key_End ? count - 1 : Math.max(0, Math.min(count - 1, recordsPanel.workspace.viewState.selection + step));
                        recordsPanel.backend.selectRow(row);
                        positionViewAtRow(row, TableView.Contain);
                        event.accepted = true;
                    } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && recordsPanel.workspace.viewState.selection >= 0) {
                        recordsPanel.detailsRequested();
                        event.accepted = true;
                    } else if (event.key === Qt.Key_C && event.modifiers & Qt.ControlModifier) {
                        recordsPanel.backend.copySelected();
                        event.accepted = true;
                    }
                }
                delegate: Rectangle {
                    id: tableCell
                    required property int row
                    required property int column
                    required property string display
                    required property string originalText
                    clip: true
                    implicitWidth: tableView.columnWidthProvider(column)
                    implicitHeight: recordsPanel.workspace.viewState.compact ? 32 : 40
                    color: recordsPanel.workspace.viewState.selection === row ? Theme.selected : row % 2 ? Theme.subtle : Theme.surface
                    Text {
                        id: cellText
                        textFormat: Text.PlainText
                        anchors {
                            fill: parent
                            leftMargin: 11
                            rightMargin: 11
                        }
                        text: tableCell.display
                        color: Theme.text
                        font.pixelSize: 12
                        verticalAlignment: Text.AlignVCenter
                        horizontalAlignment: tableView.numericColumn(tableCell.column) ? Text.AlignRight : Text.AlignLeft
                        elide: Text.ElideRight
                    }
                    TapHandler {
                        onTapped: {
                            recordsPanel.backend.selectRow(tableCell.row);
                            tableView.forceActiveFocus();
                        }
                        onDoubleTapped: {
                            recordsPanel.backend.selectRow(tableCell.row);
                            recordsPanel.detailsRequested();
                        }
                    }
                    HoverHandler {
                        id: cellHover
                    }
                    ToolTip.visible: cellHover.hovered && cellText.truncated
                    ToolTip.text: originalText
                    ToolTip.delay: 450
                    Accessible.role: Accessible.Cell
                    Accessible.name: (tableView.columnSpecs[column] || {
                            label: ""
                        }).label + ": " + originalText
                    Accessible.onPressAction: recordsPanel.backend.selectRow(tableCell.row)
                }
                Text {
                    textFormat: Text.PlainText
                    anchors.centerIn: parent
                    visible: recordsPanel.workspace.viewState.loaded && recordsPanel.workspace.viewState.tableCount === "0"
                    text: "Nenhum registro para esta seleção."
                    color: Theme.muted
                    font.pixelSize: 13
                }
                Text {
                    textFormat: Text.PlainText
                    anchors.centerIn: parent
                    visible: !recordsPanel.workspace.viewState.loaded
                    text: "Consulte um período para visualizar os registros."
                    color: Theme.muted
                    font.pixelSize: 12
                }
            }
            TaskProgress {
                objectName: "localProgress"
                anchors.top: tableHeader.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 2
                z: 2
                indeterminate: true
                visible: recordsPanel.workspace.localActivityVisible
                Accessible.name: "Atualizando registros"
            }
        }
        GridLayout {
            columns: recordsPanel.width > 480 ? 2 : 1
            columnSpacing: 12
            rowSpacing: 9
            Layout.fillWidth: true
            RowLayout {
                Layout.fillWidth: true
                AppCombo {
                    objectName: "pageSize"
                    Layout.preferredWidth: 125
                    model: [
                        {
                            label: "25 linhas",
                            value: 25
                        },
                        {
                            label: "50 linhas",
                            value: 50
                        },
                        {
                            label: "100 linhas",
                            value: 100
                        },
                        {
                            label: "200 linhas",
                            value: 200
                        }
                    ]
                    currentIndex: model.findIndex(item => item.value === recordsPanel.workspace.viewState.pageSize)
                    Accessible.name: "Linhas por página"
                    onActivated: recordsPanel.backend.setPageSize(currentValue)
                }
                Text {
                    textFormat: Text.PlainText
                    text: "Página " + recordsPanel.workspace.viewState.page + " de " + recordsPanel.workspace.viewState.pages
                    color: Theme.muted
                    font.pixelSize: 11
                }
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                Layout.fillWidth: true
                Item {
                    Layout.fillWidth: true
                }
                ActionButton {
                    objectName: "firstPage"
                    iconName: "first"
                    implicitWidth: 36
                    leftPadding: 8
                    rightPadding: 8
                    text: ""
                    Accessible.name: "Primeira página"
                    enabled: recordsPanel.workspace.viewState.loaded && !recordsPanel.workspace.viewState.busy && !recordsPanel.workspace.viewState.waiting && recordsPanel.workspace.viewState.page > 1
                    onClicked: recordsPanel.backend.setPage(1)
                    ToolTip.visible: hovered
                    ToolTip.text: "Primeira página"
                    ToolTip.delay: 450
                }
                ActionButton {
                    objectName: "previousPage"
                    iconName: "left"
                    implicitWidth: 42
                    text: ""
                    Accessible.name: "Página anterior"
                    enabled: recordsPanel.workspace.viewState.loaded && !recordsPanel.workspace.viewState.waiting && recordsPanel.workspace.viewState.page > 1 && !recordsPanel.workspace.viewState.busy
                    onClicked: recordsPanel.backend.setPage(recordsPanel.workspace.viewState.page - 1)
                }
                ActionButton {
                    objectName: "nextPage"
                    iconName: "right"
                    implicitWidth: 42
                    text: ""
                    Accessible.name: "Próxima página"
                    enabled: recordsPanel.workspace.viewState.loaded && !recordsPanel.workspace.viewState.waiting && recordsPanel.workspace.viewState.page < recordsPanel.workspace.viewState.pages && !recordsPanel.workspace.viewState.busy
                    onClicked: recordsPanel.backend.setPage(recordsPanel.workspace.viewState.page + 1)
                }
                ActionButton {
                    objectName: "lastPage"
                    iconName: "last"
                    implicitWidth: 36
                    leftPadding: 8
                    rightPadding: 8
                    text: ""
                    Accessible.name: "Última página"
                    enabled: recordsPanel.workspace.viewState.loaded && !recordsPanel.workspace.viewState.busy && !recordsPanel.workspace.viewState.waiting && recordsPanel.workspace.viewState.page < recordsPanel.workspace.viewState.pages
                    onClicked: recordsPanel.backend.setPage(recordsPanel.workspace.viewState.pages)
                    ToolTip.visible: hovered
                    ToolTip.text: "Última página"
                    ToolTip.delay: 450
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: recordsPanel.workspace.viewState.copyMessage || recordsPanel.workspace.viewState.selectedTitle || ""
                color: Theme.muted
                font.pixelSize: 11
                elide: Text.ElideRight
            }
            ActionButton {
                objectName: "detailsButton"
                text: "Detalhes"
                enabled: recordsPanel.workspace.viewState.selection >= 0
                onClicked: recordsPanel.detailsRequested()
            }
        }
    }
}
