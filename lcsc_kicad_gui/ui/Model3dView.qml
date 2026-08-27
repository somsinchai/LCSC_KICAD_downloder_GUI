import QtQuick
import QtQuick3D
import QtQuick3D.Helpers
import QtQuick3D.AssetUtils

Item {
    id: root

    property url modelSource: ""
    property bool gridVisible: true
    // Exposed so the host can read the outcome even if it connected late.
    readonly property int loaderStatus: loader.status
    readonly property string loaderError: loader.errorString
    signal loadFailed(string message)
    signal loadSucceeded()

    // Orbit state. The camera is always derived from these, never set directly,
    // so panning and rotating can't fight each other.
    property real yaw: 35
    property real pitch: 22
    property real distance: 60
    property vector3d target: Qt.vector3d(0, 0, 0)
    property real modelSpan: 10

    View3D {
        id: view
        anchors.fill: parent

        environment: SceneEnvironment {
            clearColor: "#1e2126"
            backgroundMode: SceneEnvironment.Color
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
        }

        PerspectiveCamera {
            id: camera
            clipNear: 0.1
            clipFar: 100000
        }

        // Three lights so the part reads as a solid object from any angle.
        DirectionalLight { eulerRotation.x: -35; eulerRotation.y: -70; brightness: 1.1 }
        DirectionalLight { eulerRotation.x:  35; eulerRotation.y: 120; brightness: 0.6 }
        DirectionalLight { eulerRotation.x:  85;                       brightness: 0.35 }

        Node {
            id: pivot
            RuntimeLoader {
                id: loader
                source: root.modelSource
                onStatusChanged: {
                    if (status === RuntimeLoader.Error) {
                        root.loadFailed(errorString)
                    } else if (status === RuntimeLoader.Success) {
                        root.frameModel()
                        root.loadSucceeded()
                    }
                }
                onBoundsChanged: root.frameModel()
            }
        }

        AxisHelper {
            enableXZGrid: root.gridVisible
            enableAxisLines: root.gridVisible
            visible: root.gridVisible
        }
    }

    // Left drag pans, right drag rotates.
    MouseArea {
        id: mouse
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        hoverEnabled: false
        cursorShape: pressedButtons & Qt.LeftButton ? Qt.ClosedHandCursor : Qt.ArrowCursor

        property real lastX: 0
        property real lastY: 0

        onPressed: function (event) {
            lastX = event.x
            lastY = event.y
        }

        onPositionChanged: function (event) {
            var dx = event.x - lastX
            var dy = event.y - lastY
            lastX = event.x
            lastY = event.y

            if (event.buttons & Qt.LeftButton) {
                // Pan across the camera's own plane, scaled by how far away we
                // are, so the model tracks the cursor at any zoom level.
                var k = root.distance * 0.0016
                root.target = root.target.minus(camera.right.times(dx * k))
                                         .plus(camera.up.times(dy * k))
                root.updateCamera()
            } else if (event.buttons & Qt.RightButton) {
                root.yaw -= dx * 0.4
                root.pitch = Math.max(-89, Math.min(89, root.pitch + dy * 0.3))
                root.updateCamera()
            }
        }

        onDoubleClicked: root.frameModel()

        onWheel: function (wheel) {
            var factor = Math.pow(0.9985, wheel.angleDelta.y)
            root.distance = Math.max(root.modelSpan * 0.05,
                            Math.min(root.modelSpan * 25, root.distance * factor))
            root.updateCamera()
        }
    }

    function updateCamera() {
        var ry = yaw * Math.PI / 180
        var rx = pitch * Math.PI / 180
        var horizontal = distance * Math.cos(rx)
        camera.position = Qt.vector3d(target.x + horizontal * Math.sin(ry),
                                      target.y + distance * Math.sin(rx),
                                      target.z + horizontal * Math.cos(ry))
        camera.lookAt(target)
    }

    // Recentre the geometry on the origin and pull back far enough to frame it,
    // whatever scale the model happens to arrive in.
    function frameModel() {
        var b = loader.bounds
        if (!b)
            return
        var dx = b.maximum.x - b.minimum.x
        var dy = b.maximum.y - b.minimum.y
        var dz = b.maximum.z - b.minimum.z
        pivot.position = Qt.vector3d(-(b.minimum.x + b.maximum.x) / 2,
                                     -(b.minimum.y + b.maximum.y) / 2,
                                     -(b.minimum.z + b.maximum.z) / 2)
        var diagonal = Math.sqrt(dx * dx + dy * dy + dz * dz)
        if (!(diagonal > 0))
            diagonal = 10
        modelSpan = diagonal
        target = Qt.vector3d(0, 0, 0)
        yaw = 35
        pitch = 22
        distance = diagonal * 1.6
        updateCamera()
    }

    Component.onCompleted: updateCamera()
}
