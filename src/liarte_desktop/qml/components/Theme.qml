pragma Singleton
import QtQuick

QtObject {
    property bool dark: false
    property bool reducedMotion: false
    property bool windowVisible: true
    readonly property bool motionEnabled: !reducedMotion && windowVisible
    readonly property color canvas: dark ? "#101923" : "#f5f7fa"
    readonly property color surface: dark ? "#182430" : "#ffffff"
    readonly property color subtle: dark ? "#202f3e" : "#f0f4f8"
    readonly property color line: dark ? "#334658" : "#dce4ed"
    readonly property color text: dark ? "#edf3f9" : "#20334a"
    readonly property color muted: dark ? "#b9c6d3" : "#52657b"
    readonly property color softLine: dark ? "#263746" : "#e8edf3"
    readonly property color accent: dark ? "#5bc8db" : "#087e91"
    readonly property color primary: dark ? "#245e8e" : "#103f70"
    readonly property color primaryHover: dark ? "#2c71a7" : "#174f87"
    readonly property color selected: dark ? "#244252" : "#e8f2f6"
    readonly property color hero: dark ? "#163c5d" : "#103f70"
    readonly property color heroMuted: "#c4daed"
    readonly property color hover: dark ? "#223445" : "#f6f9fc"
    readonly property int radius: 10
    readonly property int fast: motionEnabled ? 100 : 0
    readonly property color warningBg: dark ? "#302d22" : "#fff8e9"
    readonly property color warningText: dark ? "#f6db9e" : "#725516"
    readonly property color danger: dark ? "#f8b9af" : "#a33c2b"
    readonly property int motion: motionEnabled ? 160 : 0
}
