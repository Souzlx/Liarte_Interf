import QtQuick
import QtQuick.Controls

Item {
    id: chart
    property var points: []
    property string unit: "R$"
    property string seriesName: "Estoque a custo"
    property string mode: "line"
    property bool showValues: false
    property bool movingAverage: true
    property int precision: 2
    property int hoverIndex: -1
    property int selectedIndex: -1
    property int curvePaintCount: 0
    property real reveal: 1
    readonly property bool animating: revealMotion.running
    readonly property int activeIndex: hoverIndex >= 0 ? hoverIndex : selectedIndex
    readonly property var axis: {
        let low = 0, high = 0;
        for (const p of points) {
            for (const field of movingAverage ? ["value", "movingValue"] : ["value"]) {
                if (valid(p[field])) {
                    low = Math.min(low, p[field]);
                    high = Math.max(high, p[field]);
                }
            }
        }
        const rough = (high - low || 1) / 4;
        const power = Math.pow(10, Math.floor(Math.log10(rough)));
        const fraction = rough / power;
        const step = (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10) * power;
        const minimum = Math.floor(low / step) * step;
        const maximum = Math.ceil(high / step) * step;
        return {
            low: minimum,
            high: maximum > minimum ? maximum : minimum + step,
            step: step
        };
    }
    readonly property real span: axis.high - axis.low || 1
    readonly property bool compact: width < 440
    readonly property real categoryLabelWidth: 60
    readonly property real divisor: unit === "R$" ? Math.max(Math.abs(axis.high), Math.abs(axis.low)) >= 1000000 ? 1000000 : Math.max(Math.abs(axis.high), Math.abs(axis.low)) >= 10000 ? 1000 : 1 : 1
    readonly property string axisUnit: unit + (divisor === 1000000 ? " mi" : divisor === 1000 ? " mil" : "")
    readonly property int tickDigits: {
        let digits = 0, scaled = axis.step / divisor;
        while (digits < 6 && Math.abs(scaled - Math.round(scaled)) > 0.0000001) {
            digits++;
            scaled *= 10;
        }
        return digits;
    }
    readonly property var ticks: {
        const result = [];
        for (let n = axis.low; n <= axis.high + axis.step / 2; n += axis.step)
            result.push(Math.abs(n) < axis.step / 100 ? 0 : n);
        return result;
    }
    readonly property var categoryTicks: {
        const result = [];
        const last = points.length - 1;
        const gap = categoryLabelWidth + 8;
        for (let i = 0; i <= last; i++) {
            const left = categoryX(i);
            if (result.length && left - categoryX(result[result.length - 1].index) < gap)
                continue;
            if (i !== last && categoryX(last) - left < gap)
                continue;
            result.push({point: points[i], index: i});
        }
        if (last >= 0 && (!result.length || result[result.length - 1].index !== last))
            result.push({point: points[last], index: last});
        return result;
    }
    readonly property var valueTicks: {
        const result = [];
        const gap = Math.max(52, valueMetrics.advanceWidth + 14);
        for (let i = 0; i < points.length; i++) {
            if (valid(points[i].value) && (!result.length || px(i) - px(result[result.length - 1].index) >= gap))
                result.push({point: points[i], index: i});
        }
        return result;
    }
    readonly property bool hasValues: points.some(p => valid(p.value))
    readonly property bool hasAverage: movingAverage && points.some(p => valid(p.movingValue))
    readonly property string readout: {
        if (activeIndex < 0 || activeIndex >= points.length)
            return "";
        const point = points[activeIndex];
        return point.label + ": " + (point.display || formatted(point.value)) + (hasAverage && valid(point.movingValue) ? " · Média 3 meses: " + (point.movingDisplay || formatted(point.movingValue)) : "");
    }
    Accessible.role: Accessible.Graphic
    Accessible.name: seriesName + ". " + axisUnit + ". " + readout
    Accessible.description: "Use as setas para consultar os meses. Meses sem dados permanecem em branco."
    activeFocusOnTab: true
    function valid(value) {
        return typeof value === "number" && isFinite(value);
    }
    function formatted(value) {
        return valid(value) ? (unit === "R$" ? "R$ " : "") + value.toLocaleString(Qt.locale("pt_BR"), "f", precision) + (unit === "R$" ? "" : " " + unit) : "Sem dados";
    }
    function px(index) {
        return plot.width * (index + 0.5) / Math.max(1, points.length);
    }
    function categoryX(index) {
        return Math.max(0, Math.min(plot.width - categoryLabelWidth, px(index) - categoryLabelWidth / 2));
    }
    function periodLabel(period) {
        const months = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
        const month = months[Number(period.slice(5, 7)) - 1];
        return month ? month + (compact ? "\n" + period.slice(0, 4) : "/" + period.slice(2, 4)) : period;
    }
    function valueLabel(value) {
        return (value / divisor).toLocaleString(Qt.locale("pt_BR"), "f", precision);
    }
    function latestValueIndex() {
        for (let i = points.length - 1; i >= 0; i--)
            if (valid(points[i].value))
                return i;
        return -1;
    }
    function py(value) {
        return plot.height * (1 - (value - axis.low) / span);
    }
    function repaint() {
        grid.requestPaint();
        curve.requestPaint();
    }
    function select(index) {
        hoverIndex = -1;
        selectedIndex = Math.max(0, Math.min(points.length - 1, index));
    }
    Keys.onPressed: event => {
        if (!points.length)
            return;
        if (event.key === Qt.Key_Left)
            select(selectedIndex - 1);
        else if (event.key === Qt.Key_Right)
            select(selectedIndex + 1);
        else if (event.key === Qt.Key_Home)
            select(0);
        else if (event.key === Qt.Key_End)
            select(points.length - 1);
        else {
            event.accepted = false;
            return;
        }
        event.accepted = true;
    }
    onPointsChanged: {
        hoverIndex = -1;
        selectedIndex = latestValueIndex();
        revealMotion.stop();
        if (Theme.motionEnabled && visible && points.length > 1)
            revealMotion.restart();
        else
            reveal = 1;
        repaint();
    }
    onModeChanged: repaint()
    onMovingAverageChanged: repaint()
    onAxisChanged: repaint()
    onVisibleChanged: if (!visible) {
        revealMotion.stop();
        reveal = 1;
    }
    NumberAnimation {
        id: revealMotion
        target: chart
        property: "reveal"
        from: 0
        to: 1
        duration: 220
        easing.type: Easing.OutCubic
    }
    Connections {
        target: Theme
        function onDarkChanged() {
            chart.repaint();
        }
        function onMotionEnabledChanged() {
            if (!Theme.motionEnabled) {
                revealMotion.stop();
                chart.reveal = 1;
            }
        }
    }
    Rectangle {
        anchors.fill: parent
        color: "transparent"
        radius: 4
        border.color: chart.activeFocus ? Theme.accent : "transparent"
    }
    Text {
        x: 0
        y: 0
        text: chart.axisUnit
        color: Theme.muted
        font.pixelSize: 11
        font.weight: Font.Medium
        textFormat: Text.PlainText
    }
    Item {
        id: plot
        objectName: chart.objectName + "PlotArea"
        x: Math.max(46, Math.max(yMinimumMetrics.advanceWidth, yMaximumMetrics.advanceWidth) + 13)
        y: 26
        width: Math.max(1, chart.width - x - 14)
        height: Math.max(1, chart.height - (chart.compact ? 76 : 62))
        TextMetrics {
            id: yMinimumMetrics
            font.pixelSize: 11
            text: (chart.axis.low / chart.divisor).toLocaleString(Qt.locale("pt_BR"), "f", chart.tickDigits)
        }
        TextMetrics {
            id: yMaximumMetrics
            font.pixelSize: 11
            text: (chart.axis.high / chart.divisor).toLocaleString(Qt.locale("pt_BR"), "f", chart.tickDigits)
        }
        TextMetrics {
            id: valueMetrics
            font.pixelSize: 11
            text: chart.valueLabel(Math.max(Math.abs(chart.axis.low), Math.abs(chart.axis.high)))
        }
        Canvas {
            id: grid
            anchors.fill: parent
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                const c = getContext("2d");
                c.reset();
                c.lineWidth = 1;
                for (const tick of chart.ticks) {
                    c.strokeStyle = tick === 0 ? Theme.line : Theme.softLine;
                    c.globalAlpha = tick === 0 ? 1 : 0.8;
                    const y = Math.round(chart.py(tick)) + 0.5;
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
                width: plot.width
                height: plot.height
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
                onPaint: {
                    chart.curvePaintCount++;
                    const c = getContext("2d");
                    c.reset();
                    const count = chart.points.length;
                    const barWidth = Math.min(40, plot.width / Math.max(1, count) * 0.6);
                    function series(field, dashed) {
                        c.strokeStyle = dashed ? Theme.muted : Theme.accent;
                        c.fillStyle = dashed ? Theme.muted : Theme.accent;
                        c.lineWidth = dashed ? 1.5 : 2.4;
                        c.lineJoin = "round";
                        c.lineCap = "round";
                        if (chart.mode === "column" && !dashed) {
                            for (let i = 0; i < count; i++) {
                                const value = chart.points[i].value;
                                if (!chart.valid(value))
                                    continue;
                                c.fillRect(chart.px(i) - barWidth / 2, Math.min(chart.py(value), chart.py(0)), barWidth, Math.max(1, Math.abs(chart.py(value) - chart.py(0))));
                            }
                            return;
                        }
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
                                c.lineTo(chart.px(i), chart.py(value));
                            else
                                c.moveTo(chart.px(i), chart.py(value));
                            connected = true;
                        }
                        c.stroke();
                        c.setLineDash([]);
                        for (let i = 0; i < count; i++) {
                            const value = chart.points[i][field];
                            if (!chart.valid(value))
                                continue;
                            const isolated = (i === 0 || !chart.valid(chart.points[i - 1][field])) && (i === count - 1 || !chart.valid(chart.points[i + 1][field]));
                            if ((!dashed && count <= 24) || isolated) {
                                c.beginPath();
                                c.arc(chart.px(i), chart.py(value), dashed ? 2 : 3, 0, Math.PI * 2);
                                c.fill();
                            }
                        }
                    }
                    series("value", false);
                    if (chart.movingAverage)
                        series("movingValue", true);
                }
            }
        }
        Repeater {
            model: chart.showValues ? chart.valueTicks : []
            Text {
                required property var modelData
                visible: chart.valid(modelData.point.value)
                x: Math.max(0, Math.min(plot.width - width, chart.px(modelData.index) - width / 2))
                y: Math.max(0, Math.min(plot.height - height, chart.py(modelData.point.value || 0) + (modelData.point.value < 0 ? 7 : -20)))
                text: chart.valid(modelData.point.value) ? chart.valueLabel(modelData.point.value) : ""
                color: Theme.text
                font.pixelSize: 11
                font.weight: Font.Medium
                style: Text.Outline
                styleColor: Theme.surface
                textFormat: Text.PlainText
            }
        }
        Rectangle {
            visible: chart.activeIndex >= 0 && chart.activeIndex < chart.points.length
            x: chart.px(chart.activeIndex)
            width: 1
            height: parent.height
            color: Theme.accent
            opacity: 0.3
        }
        Rectangle {
            visible: chart.activeIndex >= 0 && chart.activeIndex < chart.points.length && chart.valid(chart.points[chart.activeIndex].value)
            x: chart.px(chart.activeIndex) - 5
            y: visible ? chart.py(chart.points[chart.activeIndex].value) - 5 : 0
            width: 10
            height: 10
            radius: 5
            color: Theme.surface
            border.width: 2
            border.color: Theme.accent
        }
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            enabled: chart.points.length > 0
            onPositionChanged: mouse => chart.hoverIndex = Math.max(0, Math.min(chart.points.length - 1, Math.floor(mouse.x / width * chart.points.length)))
            onExited: chart.hoverIndex = -1
            onClicked: mouse => {
                chart.select(Math.floor(mouse.x / width * chart.points.length));
                chart.forceActiveFocus();
            }
            ToolTip.visible: containsMouse && chart.readout.length > 0
            ToolTip.text: chart.readout
            ToolTip.delay: 80
        }
    }
    Repeater {
        model: chart.ticks
        Text {
            required property real modelData
            required property int index
            objectName: chart.objectName + "ValueTick" + index
            x: 0
            y: plot.y + chart.py(modelData) - height / 2
            width: plot.x - 9
            text: (modelData / chart.divisor).toLocaleString(Qt.locale("pt_BR"), "f", chart.tickDigits)
            font.pixelSize: 11
            color: Theme.muted
            horizontalAlignment: Text.AlignRight
            textFormat: Text.PlainText
        }
    }
    Repeater {
        model: chart.categoryTicks
        Text {
            required property var modelData
            objectName: chart.objectName + "CategoryTick" + modelData.index
            x: plot.x + chart.categoryX(modelData.index)
            y: plot.y + plot.height + 11
            width: chart.categoryLabelWidth
            text: chart.periodLabel(modelData.point.period)
            color: Theme.muted
            font.pixelSize: 11
            lineHeight: 1.15
            horizontalAlignment: Text.AlignHCenter
            textFormat: Text.PlainText
        }
    }
    Text {
        anchors.centerIn: plot
        visible: !chart.hasValues
        text: "Sem dados no período"
        font.pixelSize: 12
        color: Theme.muted
    }
}
