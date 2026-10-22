import QtQuick

Canvas {
    id: icon
    property string name: ""
    property color color: Theme.text
    implicitWidth: 18
    implicitHeight: 18
    onNameChanged: requestPaint()
    onColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        const c = getContext("2d");
        c.reset();
        c.scale(width / 24, height / 24);
        c.strokeStyle = color;
        c.fillStyle = color;
        c.lineWidth = 1.7;
        c.lineCap = "round";
        c.lineJoin = "round";
        const paths = {
            home: [[3, 10, 12, 3, 21, 10], [5, 9, 5, 21, 19, 21, 19, 9], [10, 21, 10, 14, 14, 14, 14, 21]],
            box: [[3, 7, 12, 3, 21, 7, 21, 18, 12, 22, 3, 18, 3, 7, 12, 11, 21, 7], [12, 11, 12, 22], [7, 5, 16, 9]],
            credit: [[3, 5, 21, 5, 21, 19, 3, 19, 3, 5], [3, 10, 21, 10], [7, 15, 11, 15]],
            chart: [[3, 3, 3, 21, 21, 21], [7, 16, 7, 11], [12, 16, 12, 6], [17, 16, 17, 9]],
            settings: [[3, 6, 21, 6], [3, 12, 21, 12], [3, 18, 21, 18], [8, 3, 8, 9], [16, 9, 16, 15], [9, 15, 9, 21]],
            download: [[12, 3, 12, 15], [7, 10, 12, 15, 17, 10], [4, 16, 4, 21, 20, 21, 20, 16]],
            file: [[14, 3, 5, 3, 5, 21, 19, 21, 19, 8, 14, 3, 14, 8, 19, 8], [8, 12, 16, 12], [8, 16, 16, 16]],
            grid: [[3, 3, 21, 3, 21, 21, 3, 21, 3, 3], [3, 9, 21, 9], [3, 15, 21, 15], [9, 3, 9, 21], [15, 3, 15, 21]],
            filter: [[4, 4, 20, 4, 14, 11, 14, 19, 10, 21, 10, 11, 4, 4]],
            weight: [[8, 7, 5, 7, 2, 21, 22, 21, 19, 7, 16, 7], [9, 7, 9, 3, 15, 3, 15, 7]],
            price: [[6, 3, 20, 3, 20, 17, 13, 22, 2, 11, 6, 3], [14, 7, 14, 8]],
            info: [[12, 11, 12, 17]],
            search: [[16, 16, 21, 21]],
            close: [[6, 6, 18, 18], [18, 6, 6, 18]],
            left: [[15, 5, 8, 12, 15, 19]],
            right: [[9, 5, 16, 12, 9, 19]],
            first: [[5, 5, 5, 19], [17, 5, 10, 12, 17, 19]],
            last: [[19, 5, 19, 19], [7, 5, 14, 12, 7, 19]],
            folder: [[3, 6, 10, 6, 12, 9, 21, 9, 21, 20, 3, 20, 3, 6]],
            refresh: [[20, 4, 20, 10, 14, 10], [4, 20, 4, 14, 10, 14]],
            check: [[4, 12, 9, 17, 20, 6]],
            sun: [[12, 2, 12, 4], [12, 20, 12, 22], [2, 12, 4, 12], [20, 12, 22, 12], [5, 5, 6.5, 6.5], [17.5, 17.5, 19, 19], [5, 19, 6.5, 17.5], [17.5, 6.5, 19, 5]],
            moon: [[19, 16, 16, 19, 11, 20, 6, 17, 4, 12, 5, 7, 8, 4, 8, 9, 11, 14, 15, 16, 19, 16]]
        };
        for (const path of (paths[name] || [])) {
            c.beginPath();
            c.moveTo(path[0], path[1]);
            for (let n = 2; n < path.length; n += 2)
                c.lineTo(path[n], path[n + 1]);
            c.stroke();
        }
        if (name === "sun" || name === "info" || name === "search") {
            c.beginPath();
            c.arc(name === "search" ? 10 : 12, name === "search" ? 10 : 12, name === "sun" ? 4.5 : name === "search" ? 6.5 : 9, 0, Math.PI * 2);
            c.stroke();
        }
        if (name === "info") {
            c.beginPath();
            c.arc(12, 7, 1, 0, Math.PI * 2);
            c.fill();
        }
        if (name === "refresh") {
            c.beginPath();
            c.arc(12, 12, 8, -2.7, -.25);
            c.stroke();
            c.beginPath();
            c.arc(12, 12, 8, .45, 2.9);
            c.stroke();
        }
    }
}
