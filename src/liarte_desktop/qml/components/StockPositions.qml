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
    readonly property bool modalOpen: sortChoice.popup.visible
    readonly property var sortOptions: [
        {value: 9, label: "Giro mensal da fonte", descending: true},
        {value: 6, label: "Valor em estoque a custo", descending: true},
        {value: 5, label: "Saldo por unidade", descending: true},
        {value: 8, label: "Última venda", descending: false},
        {value: 10, label: "Dias de estoque da fonte", descending: true},
        {value: 1, label: "Nome do produto", descending: false},
        {value: 0, label: "Código do produto", descending: false},
        {value: 2, label: "Filial", descending: false},
        {value: 3, label: "Armazém", descending: false},
        {value: 4, label: "Unidade de medida", descending: false},
        {value: 7, label: "Curva ABC", descending: false}
    ]
    readonly property string directionLabel: {
        const descending = Boolean(state.descending);
        switch (state.sortColumn) {
        case 9: return descending ? "Maior giro primeiro" : "Menor giro primeiro";
        case 6: return descending ? "Maior valor primeiro" : "Menor valor primeiro";
        case 5: return descending ? "Maior saldo primeiro" : "Menor saldo primeiro";
        case 8: return descending ? "Venda mais recente" : "Venda mais antiga";
        case 10: return descending ? "Mais dias primeiro" : "Menos dias primeiro";
        default: return descending ? "Z → A" : "A → Z";
        }
    }
    readonly property string orderingContext: {
        if (state.sortColumn === 5)
            return "Compare saldos dentro de cada unidade de medida.";
        if (state.sortColumn === 9 || state.sortColumn === 10)
            return "Indicadores ausentes ou negativos ficam ao final; os valores originais são preservados.";
        if (state.sortColumn === 8)
            return "Sem venda registrada fica ao final. Última venda não mede a idade dos lotes.";
        return "";
    }
    signal performanceRequested
    signal detailRequested
    signal sortRequested(int column)
    signal sortSelected(int column, bool descending)
    signal rowSelected(int row)
    signal pageSelected(int page)
    Layout.fillWidth: true
    spacing: 10
    GridLayout {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        columns: width >= Math.max(760, performanceAction.naturalWidth + detailAction.naturalWidth + 260) ? 3 : 1
        columnSpacing: 10
        rowSpacing: 8
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: 3
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "Posições de estoque"
                color: Theme.text
                font.pixelSize: 17
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "Saldos atuais por produto, filial e armazém"
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
        }
        ActionButton {
            id: performanceAction
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
            id: detailAction
            objectName: "stockPositionDetail"
            Layout.fillWidth: parent.columns === 1
            Layout.minimumWidth: 0
            text: "Detalhar produto"
            enabled: root.state.selectedRow >= 0 && root.state.current && root.state.task !== "load"
            iconName: "chart"
            onClicked: root.detailRequested()
        }
    }
    GridLayout {
        objectName: "stockPositionsSortBar"
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        columns: width >= Math.max(560, sortDirection.naturalWidth + 320) ? 2 : 1
        columnSpacing: 12
        rowSpacing: 8
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: 5
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "Ordenar por"
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
            AppCombo {
                id: sortChoice
                objectName: "stockPositionsSort"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                model: root.sortOptions
                currentIndex: Math.max(0, root.sortOptions.findIndex(option => option.value === root.state.sortColumn))
                enabled: root.controlsEnabled && root.state.current && !root.state.busy
                hoverEnabled: true
                Accessible.name: "Ordenar posições de estoque por"
                Accessible.description: "A ordenação considera todas as posições do recorte antes da paginação."
                ToolTip.visible: hovered
                ToolTip.text: currentText
                ToolTip.delay: 450
                onActivated: index => root.sortSelected(model[index].value, model[index].descending)
            }
        }
        ActionButton {
            id: sortDirection
            objectName: "stockPositionsSortDirection"
            Layout.fillWidth: parent.columns === 1
            Layout.minimumWidth: 0
            Layout.alignment: Qt.AlignBottom
            text: root.directionLabel
            enabled: root.controlsEnabled && root.state.current && !root.state.busy
            Accessible.name: "Inverter ordenação: " + root.directionLabel
            Accessible.description: "Alterna a direção do critério selecionado e volta à primeira página."
            ToolTip.visible: hovered || activeFocus
            ToolTip.text: "Inverter ordenação: " + root.directionLabel
            ToolTip.delay: 450
            onClicked: root.sortSelected(root.state.sortColumn, !root.state.descending)
        }
    }
    Text {
        objectName: "stockPositionsSortContext"
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        text: root.orderingContext
        visible: text.length > 0
        color: Theme.muted
        font.pixelSize: 11
        wrapMode: Text.WordWrap
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
                objectName: "stockHeader_" + column
                required property int column
                required property string display
                implicitWidth: stockTable.columnWidthProvider(headerCell.column)
                implicitHeight: 40
                color: Theme.subtle
                Text {
                    objectName: "stockHeaderText_" + headerCell.column
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
