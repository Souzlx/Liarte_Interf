import QtQuick
import QtQuick.Controls

ProgressBar {
    id: control
    implicitHeight: 6
    readonly property real renderedPosition: fillScale.xScale
    readonly property bool indeterminateAnimating: sweep.running
    padding: 0
    background: Rectangle {
        radius: 3
        color: Theme.subtle
    }
    contentItem: Item {
        clip: true
        Rectangle {
            width: parent.width
            height: parent.height
            visible: !control.indeterminate
            radius: 3
            color: Theme.accent
            transform: Scale {
                id: fillScale
                origin.x: 0
                xScale: control.position
                Behavior on xScale {
                    enabled: Theme.motionEnabled && control.visible && !control.indeterminate
                    SmoothedAnimation {
                        id: fillAnimation
                        duration: 140
                        velocity: -1
                    }
                }
            }
        }
        Rectangle {
            id: segment
            visible: control.indeterminate
            width: parent.width * 0.28
            height: parent.height
            radius: 3
            color: Theme.accent
            property real phase: 0
            x: Theme.motionEnabled ? phase * (parent.width + width) - width : (parent.width - width) / 2
            NumberAnimation on phase {
                id: sweep
                from: 0
                to: 1
                duration: 1000
                loops: Animation.Infinite
                running: control.indeterminate && control.visible && Theme.motionEnabled
            }
        }
    }
    onVisibleChanged: {
        if (!visible)
            fillAnimation.complete();
    }
    Connections {
        target: Theme
        function onMotionEnabledChanged() {
            if (!Theme.motionEnabled)
                fillAnimation.complete();
        }
    }
}
