import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: comparison
    property var rows: []
    property string basis: "CIF"
    property var reference: null
    readonly property bool detailed: width >= 760
    readonly property bool graphic: width >= 980
    readonly property real maximum: Math.max(0.001, reference || 0, ...rows.map(r => r.price || 0)) * 1.08
    signal originChosen(string name)
    spacing: 0
    RowLayout {
        Layout.fillWidth: true
        Layout.bottomMargin: 10
        spacing: 12
        Text {
            Layout.fillWidth: true
            text: "País de origem"
            color: Theme.muted
            font.pixelSize: 11
            textFormat: Text.PlainText
        }
        Item {
            visible: comparison.graphic
            Layout.preferredWidth: 140
            Layout.preferredHeight: 1
        }
        Text {
            visible: comparison.detailed && comparison.basis === "CIF"
            Layout.preferredWidth: 85
            text: "FOB/kg (US$)"
            horizontalAlignment: Text.AlignRight
            color: Theme.muted
            font.pixelSize: 11
        }
        Text {
            Layout.preferredWidth: 85
            text: comparison.basis + "/kg (US$)"
            horizontalAlignment: Text.AlignRight
            color: Theme.muted
            font.pixelSize: 11
        }
        Text {
            visible: comparison.detailed && comparison.basis === "CIF"
            Layout.preferredWidth: 90
            text: "Frete/kg (US$)"
            horizontalAlignment: Text.AlignRight
            color: Theme.muted
            font.pixelSize: 11
        }
        Text {
            Layout.preferredWidth: comparison.width < 440 ? 75 : 100
            text: "Peso (kg)"
            horizontalAlignment: Text.AlignRight
            color: Theme.muted
            font.pixelSize: 11
        }
        Text {
            visible: comparison.detailed
            Layout.preferredWidth: 85
            text: "vs. média"
            horizontalAlignment: Text.AlignRight
            color: Theme.muted
            font.pixelSize: 11
        }
    }
    Repeater {
        model: comparison.rows
        ItemDelegate {
            id: origin
            required property var modelData
            required property int index
            objectName: "priceOrigin" + index
            Layout.fillWidth: true
            implicitHeight: 53
            leftPadding: 0
            rightPadding: 0
            Accessible.name: modelData.name + ", " + comparison.basis + " por kg, " + modelData.unit + " dólares. Peso: " + modelData.kg + " kg. Filtrar esta origem."
            onClicked: comparison.originChosen(modelData.name)
            HoverHandler {
                cursorShape: Qt.PointingHandCursor
            }
            ToolTip.visible: hovered
            ToolTip.delay: 500
            ToolTip.text: modelData.name + "\n" + comparison.basis + ": US$ " + modelData.unit + "/kg · " + modelData.kg + " kg\n" + (modelData.months || "") + " com peso informado\n" + modelData.difference + " vs. média do recorte · " + modelData.monthlyChange + " vs. mês anterior\nClique para filtrar esta origem."
            background: Rectangle {
                color: origin.hovered ? Theme.hover : "transparent"
                radius: 5
                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: Theme.line
                    opacity: 0.65
                }
            }
            contentItem: RowLayout {
                spacing: 12
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        Layout.fillWidth: true
                        text: origin.modelData.name
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        text: origin.modelData.share + " do valor · " + (origin.modelData.months || "")
                        color: Theme.muted
                        font.pixelSize: 10
                        textFormat: Text.PlainText
                    }
                }
                Item {
                    visible: comparison.graphic
                    Layout.preferredWidth: 140
                    Layout.preferredHeight: 22
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width
                        height: 3
                        radius: 1.5
                        color: Theme.subtle
                    }
                    Rectangle {
                        visible: origin.modelData.price !== null
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width * (origin.modelData.price || 0) / comparison.maximum
                        height: 3
                        radius: 1.5
                        color: Theme.accent
                    }
                    Rectangle {
                        visible: comparison.reference !== null
                        x: parent.width * (comparison.reference || 0) / comparison.maximum
                        y: 3
                        width: 1
                        height: 16
                        color: Theme.muted
                    }
                    Rectangle {
                        visible: origin.modelData.price !== null
                        x: parent.width * (origin.modelData.price || 0) / comparison.maximum - 3
                        y: 8
                        width: 6
                        height: 6
                        radius: 3
                        color: Theme.accent
                    }
                }
                Text {
                    visible: comparison.detailed && comparison.basis === "CIF"
                    Layout.preferredWidth: 85
                    text: origin.modelData.fob
                    color: Theme.muted
                    horizontalAlignment: Text.AlignRight
                    font.pixelSize: 12
                }
                Text {
                    Layout.preferredWidth: 85
                    text: origin.modelData.unit
                    color: Theme.text
                    horizontalAlignment: Text.AlignRight
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                }
                Text {
                    visible: comparison.detailed && comparison.basis === "CIF"
                    Layout.preferredWidth: 90
                    text: origin.modelData.freight
                    color: Theme.muted
                    horizontalAlignment: Text.AlignRight
                    font.pixelSize: 12
                }
                Text {
                    Layout.preferredWidth: comparison.width < 440 ? 75 : 100
                    text: origin.modelData.kg
                    color: Theme.text
                    horizontalAlignment: Text.AlignRight
                    font.pixelSize: 12
                    elide: Text.ElideRight
                }
                Text {
                    visible: comparison.detailed
                    Layout.preferredWidth: 85
                    text: origin.modelData.difference
                    color: Theme.muted
                    horizontalAlignment: Text.AlignRight
                    font.pixelSize: 12
                }
            }
        }
    }
}
