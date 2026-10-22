import QtQuick
import QtQuick.Controls

ComboBox {
    id: box
    implicitHeight: 42
    font.pixelSize: 13
    leftPadding: 12
    rightPadding: 28
    textRole: "label"
    valueRole: "value"
    palette.text: Theme.text
    palette.buttonText: Theme.text
    palette.base: Theme.surface
    palette.window: Theme.surface
    palette.highlight: Theme.selected
    palette.highlightedText: Theme.text
    contentItem: Text {
        textFormat: Text.PlainText
        text: box.displayText
        color: Theme.text
        font: box.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Icon {
        x: box.width - width - 11
        y: (box.height - height) / 2
        name: "right"
        width: 13
        height: 13
        rotation: box.popup.visible ? 270 : 90
        Behavior on rotation {
            NumberAnimation {
                duration: Theme.fast
                easing.type: Easing.OutCubic
            }
        }
        color: Theme.muted
    }
    background: Rectangle {
        radius: 7
        color: Theme.surface
        border.color: box.activeFocus ? Theme.accent : Theme.line
        border.width: box.activeFocus ? 2 : 1
    }
    delegate: ItemDelegate {
        required property var model
        required property int index
        width: box.width
        height: 38
        text: model[box.textRole]
        highlighted: box.highlightedIndex === index
        contentItem: Text {
            id: optionText
            textFormat: Text.PlainText
            text: parent.text
            font: box.font
            color: Theme.text
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
        ToolTip.visible: hovered && optionText.truncated
        ToolTip.text: text
        ToolTip.delay: 450
        background: Rectangle {
            color: parent.highlighted ? Theme.selected : Theme.surface
        }
    }
    popup: Popup {
        objectName: box.objectName + "Popup"
        y: box.height + 3
        width: box.width
        padding: 4
        margins: 8
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
        implicitHeight: Math.min(contentItem.implicitHeight + 8, 315)
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: box.popup.visible ? box.delegateModel : null
            currentIndex: box.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }
        background: Rectangle {
            color: Theme.surface
            border.color: Theme.line
            radius: 5
        }
    }
}
