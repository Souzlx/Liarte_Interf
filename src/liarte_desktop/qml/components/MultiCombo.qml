import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Control {
    id: box
    property var model: []
    property var currentValues: []
    property var draftValues: []
    property string filterText: ""
    property string selectionNotice: ""
    signal valuesChosen(var values)
    readonly property alias popup: menu
    readonly property string currentValue: currentValues.length === 1 ? currentValues[0] : ""
    readonly property int currentIndex: currentValues.length ? model.findIndex(item => item.value === currentValues[0]) : 0
    readonly property string displayText: currentValues.length > 1 ? currentValues.length + " selecionados" : currentValues.length ? (model.find(item => item.value === currentValues[0]) || {
            label: currentValues[0]
        }).label : (model[0] || {
            label: "Todos"
        }).label
    readonly property var choices: {
        const key = filterText.trim().toLocaleLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        return model.filter(item => item.value && (!key || (item.label + " " + (item.keywords || "")).toLocaleLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").includes(key)));
    }
    implicitHeight: 42
    implicitWidth: 250
    padding: 12
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.role: Accessible.ComboBox
    Accessible.name: displayText
    Accessible.description: currentValues.length ? currentValues.join(", ") : displayText
    Accessible.onPressAction: menu.open()
    ToolTip.visible: hovered && (currentValues.length > 1 || label.truncated)
    ToolTip.text: currentValues.length > 1 ? currentValues.map(value => (model.find(item => item.value === value) || {
                label: value
            }).label).join("\n") : displayText
    ToolTip.delay: 600
    function toggle(value) {
        if (draftValues.includes(value))
            draftValues = draftValues.filter(item => item !== value);
        else if (draftValues.length < 200)
            draftValues = draftValues.concat([value]);
        else {
            selectionNotice = "Limite de 200 opções.";
            draftValues = draftValues.slice();
        }
    }
    function apply() {
        valuesChosen(draftValues.slice());
        menu.close();
    }
    background: Rectangle {
        radius: 7
        color: box.hovered ? Theme.hover : Theme.surface
        border.color: box.activeFocus || menu.visible ? Theme.accent : Theme.line
        border.width: box.activeFocus ? 2 : 1
    }
    contentItem: RowLayout {
        spacing: 7
        Text {
            id: label
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: box.displayText
            color: Theme.text
            font.pixelSize: 13
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
        Icon {
            name: "right"
            Layout.preferredWidth: 13
            Layout.preferredHeight: 13
            color: Theme.muted
            rotation: menu.visible ? 270 : 90
            Behavior on rotation {
                NumberAnimation {
                    duration: Theme.fast
                    easing.type: Easing.OutCubic
                }
            }
        }
    }
    TapHandler {
        onTapped: {
            box.forceActiveFocus();
            menu.open();
        }
    }
    Keys.onSpacePressed: event => {
        menu.open();
        event.accepted = true;
    }
    Keys.onReturnPressed: event => {
        menu.open();
        event.accepted = true;
    }
    Keys.onDownPressed: event => {
        menu.open();
        event.accepted = true;
    }
    Popup {
        id: menu
        objectName: box.objectName + "Popup"
        focus: true
        y: box.height + 3
        width: Math.max(box.width, 270)
        padding: 6
        margins: 8
        implicitHeight: Math.min(contentItem.implicitHeight + 12, 350)
        enter: Transition {
            NumberAnimation {
                property: "opacity"
                from: 0
                to: 1
                duration: Theme.motion
            }
        }
        exit: Transition {
            NumberAnimation {
                property: "opacity"
                from: 1
                to: 0
                duration: Theme.motion
            }
        }
        onAboutToShow: {
            box.draftValues = box.currentValues.slice();
            box.filterText = "";
            box.selectionNotice = "";
            choicesView.currentIndex = 0;
        }
        onClosed: box.forceActiveFocus()
        background: Rectangle {
            color: Theme.surface
            border.color: Theme.line
            radius: 6
        }
        contentItem: ColumnLayout {
            spacing: 6
            TextField {
                id: filterBox
                focus: true
                objectName: box.objectName + "Search"
                Layout.fillWidth: true
                implicitHeight: 38
                placeholderText: "Digite para localizar…"
                text: box.filterText
                color: Theme.text
                font.pixelSize: 12
                selectByMouse: true
                maximumLength: 150
                Accessible.name: "Localizar opções"
                background: Rectangle {
                    color: Theme.surface
                    border.color: Theme.line
                    radius: 4
                }
                onTextEdited: {
                    box.filterText = text;
                    choicesView.currentIndex = 0;
                }
                Keys.onPressed: event => {
                    if (event.key === Qt.Key_Down || event.key === Qt.Key_Up) {
                        choicesView.currentIndex = Math.max(0, Math.min(box.choices.length - 1, choicesView.currentIndex + (event.key === Qt.Key_Down ? 1 : -1)));
                        choicesView.positionViewAtIndex(choicesView.currentIndex, ListView.Contain);
                        event.accepted = true;
                    } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        if (box.choices.length)
                            box.toggle(box.choices[Math.max(0, choicesView.currentIndex)].value);
                        box.apply();
                        event.accepted = true;
                    } else if (event.key === Qt.Key_Escape) {
                        menu.close();
                        event.accepted = true;
                    }
                }
            }
            ListView {
                id: choicesView
                Layout.fillWidth: true
                Layout.fillHeight: true
                implicitHeight: Math.max(70, Math.min(contentHeight, 230))
                model: box.choices
                clip: true
                delegate: AppCheck {
                    required property var modelData
                    required property int index
                    width: choicesView.width
                    implicitHeight: 36
                    text: modelData.label
                    checked: box.draftValues.includes(modelData.value)
                    onClicked: box.toggle(modelData.value)
                    contentItem: Text {
                        id: choiceText
                        textFormat: Text.PlainText
                        text: parent.text
                        leftPadding: 30
                        color: Theme.text
                        font.pixelSize: 12
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                    background: Rectangle {
                        radius: 3
                        color: parent.hovered || choicesView.currentIndex === index ? Theme.selected : Theme.surface
                    }
                    ToolTip.visible: hovered && choiceText.truncated
                    ToolTip.text: text
                    ToolTip.delay: 500
                }
                ScrollIndicator.vertical: ScrollIndicator {}
                Label {
                    anchors.centerIn: parent
                    text: "Nenhuma opção"
                    visible: box.choices.length === 0
                    color: Theme.muted
                    font.pixelSize: 11
                }
            }
            Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                visible: box.selectionNotice.length > 0
                text: box.selectionNotice
                font.pixelSize: 10
                color: Theme.muted
            }
            RowLayout {
                Layout.fillWidth: true
                ActionButton {
                    Layout.fillWidth: true
                    text: "Limpar"
                    implicitHeight: 34
                    onClicked: box.draftValues = []
                }
                ActionButton {
                    Layout.fillWidth: true
                    text: "Aplicar" + (box.draftValues.length ? " (" + box.draftValues.length + ")" : "")
                    implicitHeight: 34
                    primary: true
                    onClicked: box.apply()
                }
            }
        }
    }
}
