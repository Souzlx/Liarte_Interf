pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "stockPositionsSection"
    required property var state
    required property var tableModel
    property bool controlsEnabled: true
    property bool compact: false
    property real viewportHeight: 700
    property alias table: stockTable
    signal performanceRequested
    signal detailRequested
    signal sortRequested(int column)
    signal rowSelected(int row)
    signal pageSelected(int page)
    Layout.fillWidth: true
    spacing: 10
    GridLayout {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        columns: width >= 760 ? 3 : 1
        columnSpacing: 10
        rowSpacing: 8
        Text {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: "Posições de estoque"
            color: Theme.text
            font.pixelSize: 17
            font.weight: Font.DemiBold
            wrapMode: Text.WordWrap
        }
        ActionButton {
            objectName: "stockPerformanceOpen"
            Layout.fillWidth: parent.columns === 1
            Layout.minimumWidth: 0
            text: "Desempenho dos produtos"
            primary: true
            enabled: root.controlsEnabled && root.state.current && !root.state.busy
            iconName: "chart"
            onClicked: root.performanceRequested()
        }
        ActionButton {
            Layout.fillWidth: parent.columns === 1
            Layout.minimumWidth: 0
            text: "Detalhar produto"
            enabled: root.state.selectedRow >= 0 && root.state.current && root.state.task !== "load"
            iconName: "chart"
            onClicked: root.detailRequested()
        }
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(390, Math.max(180, root.viewportHeight - 180))
        color: Theme.line
        clip: true
        HorizontalHeaderView {
            id: stockHeader
            enabled: root.state.current && root.state.task !== "load"
            anchors {
                top: parent.top
                left: parent.left
                right: parent.right
            }
            height: 40
            syncView: stockTable
            clip: true
            delegate: Rectangle {
                id: headerCell
                required property int column
                required property string display
                implicitWidth: stockTable.columnWidthProvider(headerCell.column)
                implicitHeight: 40
                color: Theme.subtle
                Text {
                    anchors.fill: parent
                    anchors.margins: 10
                    text: headerCell.display + (root.state.sortColumn === headerCell.column ? root.state.descending ? " ↓" : " ↑" : "")
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
                TapHandler {
                    onTapped: root.sortRequested(headerCell.column)
                }
                Accessible.role: Accessible.ColumnHeader
                Accessible.name: "Ordenar por " + headerCell.display
                Accessible.onPressAction: root.sortRequested(headerCell.column)
            }
        }
        TableView {
            id: stockTable
            enabled: root.state.current && root.state.task !== "load"
            objectName: "stockTable"
            anchors {
                top: stockHeader.bottom
                bottom: parent.bottom
                left: parent.left
                right: parent.right
            }
            model: root.tableModel
            clip: true
            activeFocusOnTab: true
            Accessible.name: "Posições de estoque. Selecione com as setas e pressione Enter para detalhar."
            Keys.onPressed: event => {
                if (event.key === Qt.Key_Down) {
                    const row = Math.min(root.tableModel.rowCount() - 1, root.state.selectedRow + 1);
                    root.rowSelected(row);
                    positionViewAtRow(row, TableView.Contain);
                } else if (event.key === Qt.Key_Up) {
                    const row = Math.max(0, root.state.selectedRow - 1);
                    root.rowSelected(row);
                    positionViewAtRow(row, TableView.Contain);
                } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && root.state.selectedRow >= 0)
                    root.detailRequested();
                else
                    event.accepted = false;
            }
            reuseItems: true
            property bool compactMode: root.compact
            onCompactModeChanged: forceLayout()
            rowSpacing: 1
            columnSpacing: 1
            boundsBehavior: Flickable.StopAtBounds
            columnWidthProvider: col => [120, 320, 80, 75, 65, 155, 180, 65, 120, 130, 130][col] || 120
            rowHeightProvider: row => compactMode ? 32 : 40
            ScrollBar.horizontal: ScrollBar {
                policy: ScrollBar.AsNeeded
            }
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }
            delegate: Rectangle {
                id: cell
                required property int row
                required property int column
                required property string display
                objectName: "stockCell_" + row + "_" + column
                implicitWidth: stockTable.columnWidthProvider(cell.column)
                implicitHeight: root.compact ? 32 : 40
                color: root.state.selectedRow === row ? Theme.selected : row % 2 ? Theme.subtle : Theme.surface
                Text {
                    id: stockCell
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    text: cell.display
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.pixelSize: 12
                    verticalAlignment: Text.AlignVCenter
                    horizontalAlignment: cell.column >= 5 && cell.column !== 7 && cell.column !== 8 ? Text.AlignRight : Text.AlignLeft
                    elide: Text.ElideRight
                }
                TapHandler {
                    onTapped: {
                        root.rowSelected(cell.row);
                        stockTable.forceActiveFocus();
                    }
                    onDoubleTapped: {
                        root.rowSelected(cell.row);
                        root.detailRequested();
                    }
                }
                HoverHandler {
                    id: cellHover
                }
                ToolTip.visible: cellHover.hovered && stockCell.truncated
                ToolTip.text: cell.display
                ToolTip.delay: 400
            }
        }
        Text {
            anchors.centerIn: parent
            visible: root.state.count === 0
            text: "Nenhuma posição encontrada. Ajuste os filtros."
            color: Theme.muted
            font.pixelSize: 12
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Text {
            Layout.fillWidth: true
            text: root.state.count + " posições"
            color: Theme.muted
            font.pixelSize: 12
        }
        ActionButton {
            text: ""
            iconName: "left"
            implicitWidth: 40
            enabled: root.controlsEnabled && root.state.current && !root.state.busy && root.state.page > 1
            Accessible.name: "Página anterior"
            onClicked: root.pageSelected(root.state.page - 1)
        }
        Text {
            text: root.state.page + " / " + root.state.pages
            color: Theme.text
            font.pixelSize: 12
        }
        ActionButton {
            text: ""
            iconName: "right"
            implicitWidth: 40
            enabled: root.controlsEnabled && root.state.current && !root.state.busy && root.state.page < root.state.pages
            Accessible.name: "Próxima página"
            onClicked: root.pageSelected(root.state.page + 1)
        }
    }
}
