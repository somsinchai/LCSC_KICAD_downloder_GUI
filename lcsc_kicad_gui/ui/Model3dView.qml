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
    // Bounds are supplied by the host from the OBJ itself; RuntimeLoader.bounds
    // is not dependable here.
    property vector3d modelMin: Qt.vector3d(0, 0, 0)
    property vector3d modelMax: Qt.vector3d(0, 0, 0)
    property bool hasExplicitBounds: false

    // Ground plane and axis triad, all sized from the part in frameModel().
    property real baseY: 0
    property real gridStep: 1
    property int gridLines: 20
    property real axisLength: 5
    readonly property real axisThin: Math.max(axisLength * 0.01, 0.002)

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

        // EasyEDA models are Z-up; Qt and the camera above are Y-up. Rotating
        // here lets the part sit on the ground plane the way it does on a board.
        Node {
            id: orient
            eulerRotation.x: -90

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
        }

        // Ground plane, sized to the part and sitting exactly underneath it so
        // it never cuts through the body. AxisHelper is fixed at 10000 units,
        // which swamps a 20 mm component, and its grid is the XZ plane.
        Node {
            id: ground
            position: Qt.vector3d(0, -root.baseY, 0)
            visible: root.gridVisible

            Model {
                eulerRotation.x: -90  // GridGeometry lies in XY; lay it flat
                geometry: GridGeometry {
                    horizontalLines: root.gridLines
                    verticalLines: root.gridLines
                    horizontalStep: root.gridStep
                    verticalStep: root.gridStep
                }
                materials: DefaultMaterial {
                    lighting: DefaultMaterial.NoLighting
                    diffuseColor: "#39414c"
                }
            }

            // Short axis triad at the origin, standing on the ground plane.
            Model {
                source: "#Cube"
                position: Qt.vector3d(root.axisLength / 2, 0, 0)
                scale: Qt.vector3d(root.axisLength / 100, root.axisThin / 100, root.axisThin / 100)
                materials: DefaultMaterial { lighting: DefaultMaterial.NoLighting; diffuseColor: "#c0554d" }
            }
            Model {
                source: "#Cube"
                position: Qt.vector3d(0, root.axisLength / 2, 0)
                scale: Qt.vector3d(root.axisThin / 100, root.axisLength / 100, root.axisThin / 100)
                materials: DefaultMaterial { lighting: DefaultMaterial.NoLighting; diffuseColor: "#5a9e5a" }
            }
            Model {
                source: "#Cube"
                position: Qt.vector3d(0, 0, root.axisLength / 2)
                scale: Qt.vector3d(root.axisThin / 100, root.axisThin / 100, root.axisLength / 100)
                materials: DefaultMaterial { lighting: DefaultMaterial.NoLighting; diffuseColor: "#4a7fc0" }
            }
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
        property bool dragging: false

        onPressed: function (event) {
            lastX = event.x
            lastY = event.y
            dragging = true
        }

        onReleased: dragging = false
        onCanceled: dragging = false

        onPositionChanged: function (event) {
            if (!dragging)
                return
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

    // A round grid spacing that puts roughly 10-16 squares across the part.
    function niceStep(span) {
        var steps = [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100]
        for (var i = 0; i < steps.length; ++i) {
            if (span / steps[i] <= 16)
                return steps[i]
        }
        return steps[steps.length - 1]
    }

    // Recentre the geometry on the origin and pull back far enough to frame it,
    // whatever scale the model happens to arrive in.
    function frameModel() {
        var lo, hi
        if (hasExplicitBounds) {
            lo = modelMin
            hi = modelMax
        } else {
            var b = loader.bounds
            if (!b)
                return
            lo = b.minimum
            hi = b.maximum
        }
        var dx = hi.x - lo.x
        var dy = hi.y - lo.y
        var dz = hi.z - lo.z
        pivot.position = Qt.vector3d(-(lo.x + hi.x) / 2,
                                     -(lo.y + hi.y) / 2,
                                     -(lo.z + hi.z) / 2)
        var diagonal = Math.sqrt(dx * dx + dy * dy + dz * dz)
        if (!(diagonal > 0))
            diagonal = 10
        modelSpan = diagonal

        // dx/dy are the board plane, dz the component height (model is Z-up).
        var footprint = Math.max(dx, dy)
        if (!(footprint > 0))
            footprint = 10
        baseY = dz / 2
        gridStep = niceStep(footprint)
        gridLines = Math.min(60, Math.max(6, Math.round(footprint * 1.6 / gridStep)))
        axisLength = footprint * 0.55

        target = Qt.vector3d(0, 0, 0)
        yaw = 35
        pitch = 22
        distance = diagonal * 1.6
        updateCamera()
    }

    Component.onCompleted: updateCamera()
}
