import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: field
    required property string fieldKey
    property string title: ""
    readonly property var option: inventory.options.find(o => o.key === fieldKey) || ({
            label: title,
            values: []
        })
    spacing: 5
    Text {
        text: field.title || field.option.label
        textFormat: Text.PlainText
        color: Theme.muted
        font.pixelSize: 11
        font.weight: Font.DemiBold
    }
    AppCombo {
        objectName: "stockFilter_" + field.fieldKey
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        model: field.option.values
        currentIndex: Math.max(0, model.findIndex(o => o.value === (inventory.state.selection[field.fieldKey] || "")))
        Accessible.name: field.title || field.option.label
        onActivated: inventory.setFilter(field.fieldKey, currentValue)
    }
}
