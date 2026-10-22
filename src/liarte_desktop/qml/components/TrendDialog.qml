import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AppDialog {
    id: dialog
    property var series: ({
            points: [],
            label: "",
            tableUnit: "",
            rollingLabel: ""
        })
    property string contextLabel: ""
    readonly property bool withRolling: Boolean(series.rollingLabel)
    property bool copied: false
    signal copyRequested
    title: "Valores mensais · " + (series.label || "")
    width: Math.min(660, parent ? parent.width - 40 : 660)
    onOpened: copied = false
    onSeriesChanged: copied = false
    Text {
        Layout.fillWidth: true
        text: dialog.contextLabel
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Theme.muted
        font.pixelSize: 11
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 12
        Text {
            Layout.preferredWidth: 66
            text: "Mês"
            color: Theme.muted
            font.pixelSize: 11
        }
        Text {
            Layout.fillWidth: true
            text: "Mensal (" + (dialog.series.tableUnit || "") + ")"
            horizontalAlignment: Text.AlignRight
            color: Theme.muted
            font.pixelSize: 11
        }
        Text {
            visible: dialog.withRolling
            Layout.fillWidth: true
            text: "Média 3m (" + (dialog.series.tableUnit || "") + ")"
            horizontalAlignment: Text.AlignRight
            color: Theme.muted
            font.pixelSize: 11
        }
    }
    Repeater {
        model: dialog.visible ? dialog.series.points : []
        Rectangle {
            required property var modelData
            required property int index
            objectName: "trendDataRow" + index
            Layout.fillWidth: true
            implicitHeight: 38
            radius: 4
            color: index % 2 ? Theme.subtle : "transparent"
            Accessible.role: Accessible.StaticText
            Accessible.name: modelData.label + ". Mensal: " + modelData.tableValue + (dialog.withRolling ? ". Média de três meses: " + modelData.tableMoving : "") + ". " + dialog.series.tableUnit
            RowLayout {
                anchors.fill: parent
                anchors.margins: 5
                spacing: 12
                Text {
                    Layout.preferredWidth: 61
                    text: modelData.period.slice(5) + "/" + modelData.period.slice(0, 4)
                    color: Theme.text
                    font.pixelSize: 12
                }
                Text {
                    Layout.fillWidth: true
                    text: modelData.tableValue
                    horizontalAlignment: Text.AlignRight
                    elide: Text.ElideRight
                    color: Theme.text
                    font.pixelSize: 12
                }
                Text {
                    visible: dialog.withRolling
                    Layout.fillWidth: true
                    text: modelData.tableMoving
                    horizontalAlignment: Text.AlignRight
                    elide: Text.ElideRight
                    color: Theme.muted
                    font.pixelSize: 12
                }
            }
        }
    }
    Text {
        Layout.fillWidth: true
        text: dialog.withRolling ? dialog.series.rollingLabel + ". Calculada apenas com meses do período selecionado. — indica valor indisponível." : "Variação em relação ao mês anterior da seleção. — indica ausência de base comparável."
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Theme.muted
        font.pixelSize: 11
    }
    footer: Item {
        implicitHeight: 57
        RowLayout {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 12
            ActionButton {
                objectName: "copyTrendValues"
                text: dialog.copied ? "Copiado" : "Copiar valores"
                enabled: dialog.series.points.length > 0
                onClicked: dialog.copyRequested()
            }
            ActionButton {
                text: "Fechar"
                onClicked: dialog.close()
            }
        }
    }
}
