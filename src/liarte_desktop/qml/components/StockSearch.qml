import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

FocusScope {
    id: field
    implicitHeight: 42
    property var suggestions: ({
            items: [],
            count: 0
        })
    property int highlighted: -1
    property string selectedCode: ""
    readonly property bool popupVisible: completions.visible
    function focusSearch() {
        input.forceActiveFocus();
        input.selectAll();
    }
    function sync() {
        const selection = inventory.state.selection;
        const code = selection.product || "";
        const expected = code ? inventory.state.productLabel : selection.search || "";
        if (code !== selectedCode || input.text !== expected) {
            selectedCode = code;
            input.text = expected;
            completions.close();
        }
    }
    function suggest() {
        suggestions = inventory.searchProducts(selectedCode ? "" : input.text);
        highlighted = -1;
        if (input.activeFocus && field.enabled && field.visible)
            completions.open();
    }
    function choose(index) {
        if (index < 0 || index >= suggestions.items.length)
            return;
        inventory.setFilter("product", suggestions.items[index].code);
        completions.close();
        input.forceActiveFocus();
    }
    function clear() {
        inventory.setFilter("product", "");
        inventory.setFilter("search", "");
        input.text = "";
        completions.close();
        input.forceActiveFocus();
    }
    function move(delta) {
        if (!completions.visible)
            suggest();
        if (!suggestions.items.length) {
            highlighted = -1;
            return;
        }
        highlighted = Math.max(0, Math.min(suggestions.items.length - 1, highlighted + delta));
        results.positionViewAtIndex(highlighted, ListView.Contain);
    }
    onVisibleChanged: if (!visible)
        completions.close()
    onEnabledChanged: if (!enabled)
        completions.close()
    Connections {
        target: inventory
        function onChanged() {
            field.sync();
        }
    }
    TextField {
        id: input
        objectName: "stockSearch"
        anchors.fill: parent
        leftPadding: 36
        rightPadding: 38
        placeholderText: "Código, nome do produto ou grupo"
        placeholderTextColor: Theme.muted
        color: Theme.text
        font.pixelSize: 13
        selectByMouse: true
        Accessible.name: "Buscar produto por código, nome ou grupo"
        Accessible.description: "Digite para filtrar. Use as setas e Enter para selecionar uma sugestão. Esc fecha as sugestões."
        onTextEdited: {
            // The controller and suggestion index accept at most 200 search
            // characters. Limit edits without truncating a selected product's
            // full label, which is also shown in this field.
            const typed = text.match(/^[\s\S]{0,200}/u)[0];
            if (text !== typed)
                text = typed;
            if (field.selectedCode)
                inventory.setFilter("product", "");
            inventory.setFilter("search", typed);
            field.suggest();
        }
        Keys.onDownPressed: event => {
            field.move(1);
            event.accepted = true;
        }
        Keys.onUpPressed: event => {
            field.move(-1);
            event.accepted = true;
        }
        Keys.onEscapePressed: event => {
            completions.close();
            event.accepted = true;
        }
        Keys.onReturnPressed: event => {
            if (completions.visible && field.highlighted >= 0)
                field.choose(field.highlighted);
            else
                completions.close();
            event.accepted = true;
        }
        Keys.onEnterPressed: event => {
            if (completions.visible && field.highlighted >= 0)
                field.choose(field.highlighted);
            else
                completions.close();
            event.accepted = true;
        }
        Keys.onTabPressed: event => {
            completions.close();
            event.accepted = false;
        }
        background: Rectangle {
            color: field.selectedCode ? Theme.selected : Theme.surface
            border.color: input.activeFocus ? Theme.accent : Theme.line
            radius: 7
        }
    }
    Icon {
        x: 11
        anchors.verticalCenter: parent.verticalCenter
        width: 16
        height: 16
        name: "search"
        color: Theme.muted
    }
    ToolButton {
        objectName: "clearStockSearch"
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: 36
        height: 36
        visible: input.text.length > 0
        Accessible.name: "Limpar busca por produto"
        text: "×"
        font.pixelSize: 20
        onClicked: field.clear()
        ToolTip.visible: hovered
        ToolTip.text: "Limpar busca"
    }
    Popup {
        id: completions
        objectName: "stockSuggestions"
        property real roomBelow: Overlay.overlay ? Overlay.overlay.height - field.mapToItem(Overlay.overlay, 0, field.height).y - 16 : 320
        property real roomAbove: Overlay.overlay ? field.mapToItem(Overlay.overlay, 0, 0).y - 16 : 320
        x: 0
        y: roomBelow >= height || roomBelow >= roomAbove ? field.height + 5 : -height - 5
        width: field.width
        height: Math.min(410, Math.max(100, Math.max(roomBelow, roomAbove)), 46 + Math.max(1, field.suggestions.items.length) * 57)
        padding: 5
        focus: false
        modal: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle {
            color: Theme.surface
            radius: 8
            border.color: Theme.line
        }
        contentItem: ColumnLayout {
            spacing: 4
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 9
                Layout.preferredHeight: 28
                verticalAlignment: Text.AlignVCenter
                text: field.suggestions.count ? field.suggestions.count + " produtos · ↑ ↓ para selecionar" : "Nenhum produto encontrado"
                color: Theme.muted
                font.pixelSize: 11
                elide: Text.ElideRight
                textFormat: Text.PlainText
            }
            ListView {
                id: results
                objectName: "stockSuggestionList"
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                reuseItems: true
                boundsBehavior: Flickable.StopAtBounds
                currentIndex: field.highlighted
                model: field.suggestions.items
                ScrollBar.vertical: ScrollBar {}
                delegate: ItemDelegate {
                    id: suggestion
                    required property var modelData
                    required property int index
                    width: results.width
                    height: 57
                    padding: 9
                    focusPolicy: Qt.NoFocus
                    hoverEnabled: true
                    Accessible.name: modelData.code + ". " + modelData.name + ". Saldo " + modelData.balance
                    onClicked: field.choose(index)
                    background: Rectangle {
                        color: suggestion.index === field.highlighted ? Theme.selected : suggestion.hovered ? Theme.hover : "transparent"
                        radius: 5
                    }
                    contentItem: ColumnLayout {
                        spacing: 3
                        Text {
                            Layout.fillWidth: true
                            text: suggestion.modelData.code + " · " + suggestion.modelData.name
                            color: Theme.text
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                        }
                        Text {
                            Layout.fillWidth: true
                            text: suggestion.modelData.group + " · " + suggestion.modelData.balance
                            color: Theme.muted
                            font.pixelSize: 11
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                        }
                    }
                    ToolTip.visible: hovered
                    ToolTip.text: modelData.code + " · " + modelData.name + "\n" + modelData.balance
                    ToolTip.delay: 500
                }
            }
        }
        enter: Transition {
            NumberAnimation {
                property: "opacity"
                from: 0
                to: 1
                duration: Theme.motionEnabled ? 80 : 0
            }
        }
    }
}
