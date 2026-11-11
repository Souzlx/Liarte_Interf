pragma Singleton
import QtQuick

QtObject {
    property bool dark: false
    property bool reducedMotion: false
    property bool windowVisible: true
    readonly property bool motionEnabled: !reducedMotion && windowVisible
    readonly property color canvas: dark ? "#101923" : "#f4f6f8"
    readonly property color surface: dark ? "#182430" : "#ffffff"
    readonly property color subtle: dark ? "#223142" : "#f0f3f8"
    readonly property color line: dark ? "#35485e" : "#e2e7ef"
    readonly property color text: dark ? "#edf3f9" : "#1d293d"
    readonly property color muted: dark ? "#b9c6d3" : "#5c6f8a"
    readonly property color softLine: dark ? "#2b3c50" : "#eaf0f6"
    readonly property color accent: dark ? "#5bc8db" : "#067a94"
    // Text on actions and navigation retains AA contrast with white. Charts
    // retain the brighter reference blue without using it for small text.
    readonly property color primary: dark ? "#2865ce" : "#2366dc"
    readonly property color primaryHover: dark ? "#2b6bd7" : "#1d58c1"
    readonly property color primaryPressed: dark ? "#1d4a9a" : "#164ba9"
    readonly property color selected: dark ? "#263d5d" : "#eaf1ff"
    readonly property color hero: dark ? "#163c5d" : "#154877"
    readonly property color heroMuted: "#c4daed"
    readonly property color hover: dark ? "#223445" : "#f5f8fc"
    readonly property color chartBlue: dark ? "#78a5ff" : "#3478f6"
    readonly property color chartReference: dark ? "#93a9c2" : "#8195ae"
    readonly property color iconTint: dark ? "#263c60" : "#eaf1ff"
    readonly property color iconColor: dark ? "#93b8ff" : "#2366dc"
    readonly property color sidebar: "#101d31"
    readonly property color sidebarText: "#b9c7da"
    readonly property color sidebarMuted: "#8b9fb9"
    readonly property color sidebarHover: "#1b2b42"
    readonly property color sidebarLine: "#293a51"
    readonly property color navActive: "#2e70e9"
    readonly property color navActiveText: "#ffffff"
    readonly property color topbar: surface
    readonly property color focus: chartBlue
    readonly property color success: dark ? "#62d7b1" : "#107b5c"
    readonly property color successIndicator: "#159a72"
    readonly property color warningIndicator: "#d99a22"
    readonly property color dangerIndicator: "#d95858"
    readonly property string fontFamily: "Segoe UI"
    readonly property int sidebarWidth: 204
    readonly property int topbarHeight: 60
    readonly property int spaceXs: 4
    readonly property int spaceSm: 8
    readonly property int spaceMd: 12
    readonly property int spaceLg: 16
    readonly property int spaceXl: 24
    readonly property int space2xl: 32
    readonly property int radius: 13
    readonly property int controlRadius: 8
    readonly property int fast: motionEnabled ? 100 : 0
    readonly property color warningBg: dark ? "#302d22" : "#fff8e9"
    readonly property color warningText: dark ? "#f6db9e" : "#725516"
    readonly property color danger: dark ? "#f8b9af" : "#b53535"
    readonly property int motion: motionEnabled ? 160 : 0
}
