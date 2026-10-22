import QtQuick
import QtQuick.Window

Item {
    implicitWidth: 150
    implicitHeight: implicitWidth * 725 / 2167
    Image {
        anchors.fill: parent
        fillMode: Image.PreserveAspectFit
        sourceSize.width: Math.ceil(width * Screen.devicePixelRatio)
        source: Theme.dark ? "image://liarte/dark" : "image://liarte/light"
    }
    Accessible.role: Accessible.Graphic
    Accessible.name: "LIARTE Metalquímica"
}
