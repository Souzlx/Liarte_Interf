import QtQuick
import QtQuick.Controls

Item {
    id: chart
    property var points: []
    property string unit: "US$ mi"
    property int precision: 3
    property int hoverIndex: -1
    property int selectedIndex: -1
    property bool zoomed: false
    property bool allowNegative: false
    readonly property int activeIndex: hoverIndex >= 0 ? hoverIndex : selectedIndex
    readonly property var extent: {
        let low = Infinity, high = 0;
        for (const point of points) {
            for (const value of [point.value, point.movingValue]) {
                if (valid(value)) {
                    low = Math.min(low, value);
                    high = Math.max(high, value);
                }
            }
        }
        return {
            low: isFinite(low) ? low : 0,
            high: high
        };
    }
    readonly property real paddingRange: Math.max(extent.high - extent.low, extent.high * 0.05, Number.MIN_VALUE)
    readonly property real minimum: allowNegative && extent.low < 0 ? extent.low - paddingRange * 0.12 : zoomed && extent.high > 0 ? Math.max(0, extent.low - paddingRange * 0.45) : 0
    readonly property real span: maximum > minimum ? maximum - minimum : 1
    readonly property bool croppedAxis: minimum > 0
    readonly property string readout: hoverText
    property real reveal: 1
    property int curvePaintCount: 0
    readonly property bool animating: revealAnimation.running
    readonly property real maximum: allowNegative ? (extent.high > 0 ? extent.high + paddingRange * 0.12 : extent.low < 0 ? 0 : 1) : extent.high > 0 ? (zoomed ? extent.high + paddingRange * 0.15 : extent.high * 1.12) : 1
    readonly property real plotLeft: plot.x
    readonly property real plotWidth: plot.width
    readonly property real categoryLabelWidth: Math.ceil(monthMetrics.advanceWidth) + 14
    readonly property real axisStep: {
        const rough = span / (plot.height < 160 ? 3 : 4);
        const power = Math.pow(10, Math.floor(Math.log10(rough)));
        const fraction = rough / power;
        return (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10) * power;
    }
    readonly property var axisTicks: {
        const result = [];
        const first = Math.ceil(minimum / axisStep) * axisStep;
        for (let value = first; value <= maximum + axisStep * 0.000001 && result.length < 20; value += axisStep)
            result.push(Math.abs(value) < axisStep / 1000 ? 0 : value);
        return result;
    }
    readonly property real axisLabelWidth: Math.max(0, ...axisTicks.map(value => axisMetrics.advanceWidth(axisLabel(value))))
    readonly property var ticks: {
        if (!points.length)
            return [];
        const interval = Math.max(1, Math.ceil((points.length - 1) * categoryLabelWidth / plot.width));
        const result = points.map((p, i) => ({period: p.period, pointIndex: i})).filter((p, i) => i % interval === 0);
        const last = points.length - 1;
        if (result[result.length - 1].pointIndex !== last) {
            if (result.length > 1 && (last - result[result.length - 1].pointIndex) * plot.width / Math.max(1, last) < categoryLabelWidth)
                result.pop();
            result.push({period: points[last].period, pointIndex: last});
        }
        return result;
    }
    readonly property string hoverText: {
        if (activeIndex < 0 || activeIndex >= points.length)
            return "";
        const point = points[activeIndex];
        let label = point.label + ": " + (point.display || formatted(point.value));
        if (valid(point.movingValue))
            label += "\nMédia de 3 meses: " + (point.movingDisplay || formatted(point.movingValue));
        return label;
    }
    Accessible.role: Accessible.Graphic
    Accessible.name: "Evolução mensal, " + unit + ". " + points.length + " meses. " + readout
    activeFocusOnTab: true
    Accessible.focusable: true
    Accessible.description: (croppedAxis ? "Eixo ajustado. " : "") + "Use setas, Home e End para ler os meses. Ver valores abre a tabela completa."
    function valid(value) {
        return typeof value === "number" && isFinite(value);
    }
    function formatted(value) {
        return valid(value) ? value.toLocaleString(Qt.locale("pt_BR"), "f", precision) + " " + unit : "Sem valor disponível";
    }
    function categoryLabel(period) {
        if (!/^[0-9]{4}-[0-9]{2}$/.test(period))
            return period;
        return ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"][Number(period.slice(5)) - 1] + "/" + period.slice(2, 4);
    }
    function axisLabel(value) {
        if (value === 0)
            return "0";
        if (Math.abs(value) < 0.001 || Math.abs(value) >= 1000000000)
            return value.toExponential(1).replace(".", ",");
        let digits = 0, scaled = axisStep;
        while (digits < 6 && Math.abs(scaled - Math.round(scaled)) > 0.0000001) {
            digits++;
            scaled *= 10;
        }
        return value.toLocaleString(Qt.locale("pt_BR"), "f", digits);
    }
    function yValue(value, size) {
        return size - (value - minimum) / span * size;
    }
    function selectPoint(index) {
        hoverIndex = -1;
        if (!points.length) {
            selectedIndex = -1;
            return;
        }
        selectedIndex = Math.max(0, Math.min(points.length - 1, index));
    }
    Keys.onPressed: event => {
        if (!points.length)
            return;
        if (event.key === Qt.Key_Left)
            selectPoint(selectedIndex - 1);
        else if (event.key === Qt.Key_Right)
            selectPoint(selectedIndex + 1);
        else if (event.key === Qt.Key_Home)
            selectPoint(0);
        else if (event.key === Qt.Key_End)
            selectPoint(points.length - 1);
        else {
            event.accepted = false;
            return;
        }
        event.accepted = true;
    }
    onMinimumChanged: {
        grid.requestPaint();
        curve.requestPaint();
    }
    onMaximumChanged: {
        grid.requestPaint();
        curve.requestPaint();
    }
    onAxisTicksChanged: grid.requestPaint()
    Rectangle {
        anchors.fill: parent
        visible: chart.activeFocus
        radius: 4
        color: "transparent"
        border.color: Theme.accent
    }
    function maxValue() {
        return maximum;
    }
    onPointsChanged: {
        hoverIndex = -1;
        selectedIndex = points.length - 1;
        revealAnimation.stop();
        if (!Theme.motionEnabled || !visible || points.length < 2)
            reveal = 1;
        else
            revealAnimation.restart();
        curve.requestPaint();
    }
    onVisibleChanged: {
        if (!visible) {
            revealAnimation.stop();
            reveal = 1;
        }
    }
    NumberAnimation {
        id: revealAnimation
        target: chart
        property: "reveal"
        from: 0
        to: 1
        duration: 260
        easing.type: Easing.OutCubic
    }
    Connections {
        target: Theme
        function onDarkChanged() {
            grid.requestPaint();
            curve.requestPaint();
        }
        function onMotionEnabledChanged() {
            if (!Theme.motionEnabled) {
                revealAnimation.stop();
                chart.reveal = 1;
            }
        }
    }
    TextMetrics {
        id: monthMetrics
        font.pixelSize: 10
        text: "set/26"
    }
    FontMetrics {
        id: axisMetrics
        font.pixelSize: 10
    }
    Text {
        objectName: "monthlyAxisUnit"
        x: 0
        y: 0
        width: parent.width
        text: chart.unit
        textFormat: Text.PlainText
        color: Theme.muted
        font.pixelSize: 10
        elide: Text.ElideRight
    }
    Item {
        id: plot
        x: Math.max(36, Math.ceil(chart.axisLabelWidth) + 14)
        y: 24
        width: Math.max(1, chart.width - x - 18)
        height: Math.max(1, chart.height - 56)
        Canvas {
            id: grid
            anchors.fill: parent
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                const c = getContext("2d");
                c.reset();
                c.lineWidth = 1;
                for (const tick of chart.axisTicks) {
                    c.strokeStyle = tick === 0 ? Theme.line : Theme.softLine;
                    const y = Math.round(chart.yValue(tick, height)) + 0.5;
                    c.beginPath();
                    c.moveTo(0, y);
                    c.lineTo(width, y);
                    c.stroke();
                }
                if (chart.allowNegative && chart.minimum < 0 && chart.maximum > 0) {
                    const y = chart.yValue(0, height);
                    c.strokeStyle = Theme.muted;
                    c.beginPath();
                    c.moveTo(0, y);
                    c.lineTo(width, y);
                    c.stroke();
                }
            }
        }
        Item {
            width: plot.width * chart.reveal
            height: plot.height
            clip: chart.reveal < 1
            Canvas {
                id: curve
                objectName: "trendCurve"
                // Animate scene-graph clipping, never redraw one texture per frame.
                width: plot.width
                height: plot.height
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
                onPaint: {
                    chart.curvePaintCount++;
                    const c = getContext("2d");
                    c.reset();
                    const count = chart.points.length;
                    if (!count)
                        return;
                    const px = i => count === 1 ? width / 2 : i * width / (count - 1);
                    const py = value => chart.yValue(value, height);
                    if (!chart.allowNegative && !chart.croppedAxis && count > 1 && chart.points.every(p => chart.valid(p.value))) {
                        c.beginPath();
                        c.moveTo(px(0), height);
                        for (let i = 0; i < count; i++)
                            c.lineTo(px(i), py(chart.points[i].value));
                        c.lineTo(px(count - 1), height);
                        c.closePath();
                        const gradient = c.createLinearGradient(0, 0, 0, height);
                        gradient.addColorStop(0, Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.14));
                        gradient.addColorStop(1, Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.015));
                        c.fillStyle = gradient;
                        c.fill();
                    }
                    function draw(field, color, dashed) {
                        c.strokeStyle = color;
                        c.fillStyle = color;
                        c.lineWidth = dashed ? 1.6 : 2.5;
                        c.lineJoin = "round";
                        c.lineCap = "round";
                        c.setLineDash(dashed ? [5, 4] : []);
                        c.beginPath();
                        let connected = false;
                        for (let i = 0; i < count; i++) {
                            const value = chart.points[i][field];
                            if (!chart.valid(value)) {
                                connected = false;
                                continue;
                            }
                            if (connected)
                                c.lineTo(px(i), py(value));
                            else
                                c.moveTo(px(i), py(value));
                            connected = true;
                        }
                        c.stroke();
                        c.setLineDash([]);
                        // Isolated observations (including the first complete rolling window)
                        // need a marker; null points never become zero or get connected.
                        for (let i = 0; i < count; i++) {
                            const value = chart.points[i][field];
                            if (chart.valid(value) && ((!dashed && count <= 12) || ((i === 0 || !chart.valid(chart.points[i - 1][field])) && (i === count - 1 || !chart.valid(chart.points[i + 1][field]))))) {
                                c.beginPath();
                                c.arc(px(i), py(value), dashed ? 2.5 : 3.5, 0, Math.PI * 2);
                                c.fill();
                            }
                        }
                    }
                    draw("value", Theme.accent, false);
                    draw("movingValue", Theme.muted, true);
                }
            }
        }
        Rectangle {
            visible: chart.activeIndex >= 0 && chart.activeIndex < chart.points.length && chart.valid(chart.points[chart.activeIndex].value)
            x: 0
            y: visible ? chart.yValue(chart.points[chart.activeIndex].value, plot.height) : 0
            width: plot.width
            height: 1
            color: Theme.accent
            opacity: 0.18
        }
        Item {
            visible: chart.activeIndex >= 0 && chart.activeIndex < chart.points.length
            x: chart.points.length < 2 ? plot.width / 2 : chart.activeIndex * plot.width / (chart.points.length - 1)
            height: plot.height
            Rectangle {
                width: 1
                height: parent.height
                color: Theme.muted
                opacity: 0.65
            }
            Rectangle {
                visible: chart.activeIndex >= 0 && chart.points[chart.activeIndex] !== undefined && chart.valid(chart.points[chart.activeIndex].value)
                x: -4
                y: chart.activeIndex >= 0 && chart.points[chart.activeIndex] ? chart.yValue(chart.points[chart.activeIndex].value || 0, plot.height) - 4 : 0
                width: 8
                height: 8
                radius: 4
                color: Theme.surface
                border.width: 2
                border.color: Theme.accent
            }
        }
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            onClicked: mouse => {
                chart.selectPoint(Math.round(mouse.x / width * (chart.points.length - 1)));
                chart.forceActiveFocus(Qt.MouseFocusReason);
            }
            enabled: chart.points.length > 0
            onPositionChanged: mouse => chart.hoverIndex = Math.max(0, Math.min(chart.points.length - 1, Math.round(mouse.x / width * (chart.points.length - 1))))
            onExited: chart.hoverIndex = -1
            ToolTip.visible: containsMouse && chart.hoverText.length > 0
            ToolTip.text: chart.hoverText
            ToolTip.delay: 80
        }
    }
    Repeater {
        model: chart.axisTicks
        Text {
            required property real modelData
            required property int index
            objectName: "monthlyAxisTick" + index
            textFormat: Text.PlainText
            x: 0
            y: plot.y + chart.yValue(modelData, plot.height) - implicitHeight / 2
            width: plot.x - 10
            horizontalAlignment: Text.AlignRight
            text: chart.axisLabel(modelData)
            color: Theme.muted
            font.pixelSize: 10
        }
    }
    Repeater {
        model: chart.ticks
        Text {
            required property var modelData
            textFormat: Text.PlainText
            objectName: "monthTick" + modelData.pointIndex
            x: Math.max(0, Math.min(chart.width - width, plot.x + (chart.points.length === 1 ? plot.width / 2 : modelData.pointIndex * plot.width / (chart.points.length - 1)) - width / 2))
            y: plot.y + plot.height + 10
            width: chart.categoryLabelWidth - 8
            text: chart.categoryLabel(modelData.period)
            color: Theme.muted
            font.pixelSize: 10
            horizontalAlignment: Text.AlignHCenter
        }
    }
}
