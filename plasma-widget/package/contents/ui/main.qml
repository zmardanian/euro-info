import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls

import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as Plasma5Support


PlasmoidItem {

    id: root

    width: 620
    height: 760

    property var articles: []
    property var weather: ({})
    property string statusText: "Starting…"
    property string activeFilter: "ALL"
    property string searchText: ""
    property bool loading: false

    // Five minutes.
    property int refreshSeconds: 300


    Plasmoid.icon: "globe"
    Plasmoid.title: "Euro Info"

    // Always prefer the full news representation.
    preferredRepresentation:
        fullRepresentation

    toolTipMainText:
        "Euro Info"

    toolTipSubText:
        statusText


    // -----------------------------------------------------------------
    // DATA
    // -----------------------------------------------------------------

    function refresh() {

        if (loading)
            return

        loading = true
        statusText = "Updating…"

        var bridge = decodeURIComponent(Qt.resolvedUrl("../code/bridge.sh").toString().replace(/^file:\/\//, ""))
        executable.exec("bash '" + bridge.replace(/'/g, "'\\''") + "'")
    }


    function applyPayload(raw) {

        try {

            var payload =
                JSON.parse(raw)

            articles =
                payload.articles || []

            weather =
                payload.weather || {}

            statusText =
                payload.status ||
                (articles.length + " stories")

        } catch (e) {

            statusText =
                "Data error: " + e
        }

        loading = false
    }


    function categoryOf(article) {

        return article.category ||
               "GENERAL"
    }


    function visibleArticles() {

        var query =
            searchText.trim().toLowerCase()

        var result = []

        for (
            var i = 0;
            i < articles.length;
            ++i
        ) {

            var article =
                articles[i]

            var category =
                categoryOf(article)


            if (
                activeFilter !== "ALL" &&
                category !== activeFilter
            ) {
                continue
            }


            if (query.length > 0) {

                var searchable =
                    (
                        (article.title || "") +
                        " " +
                        (article.source || "") +
                        " " +
                        category
                    ).toLowerCase()

                if (
                    searchable.indexOf(query) === -1
                ) {
                    continue
                }
            }

            result.push(article)
        }

        return result
    }


    function openArticle(url) {

        if (
            url &&
            /^https?:\/\/[^\s]+$/i.test(url)
        ) {
            Qt.openUrlExternally(url)
        }
    }


    // -----------------------------------------------------------------
    // PYTHON BACKEND EXECUTION
    // -----------------------------------------------------------------

    Plasma5Support.DataSource {

        id: executable

        engine: "executable"

        connectedSources: []

        function exec(command) {
            connectSource(command)
        }


        onNewData:
            function(source, data) {

                disconnectSource(source)

                var exitCode =
                    Number(data["exit code"])


                if (
                    exitCode !== 0
                ) {

                    root.statusText =
                        "Update failed"

                    root.loading =
                        false

                    return
                }


                root.applyPayload(
                    String(
                        data.stdout || ""
                    )
                )
            }
    }


    // -----------------------------------------------------------------
    // AUTO REFRESH
    // -----------------------------------------------------------------

    Timer {

        interval:
            root.refreshSeconds * 1000

        repeat: true
        running: true
        triggeredOnStart: false

        onTriggered:
            root.refresh()
    }


    Component.onCompleted:
        root.refresh()


    // -----------------------------------------------------------------
    // FULL REPRESENTATION
    // -----------------------------------------------------------------

    fullRepresentation: Item {

        id: panel

        Layout.minimumWidth:
            560

        Layout.minimumHeight:
            620

        Layout.preferredWidth:
            620

        Layout.preferredHeight:
            760


        // -------------------------------------------------------------
        // BACKGROUND
        // -------------------------------------------------------------

        Rectangle {

            anchors.fill:
                parent

            radius:
                18

            color:
                Qt.rgba(
                    0.055,
                    0.065,
                    0.08,
                    0.97
                )

            border.width:
                1

            border.color:
                Qt.rgba(
                    1,
                    1,
                    1,
                    0.09
                )
        }


        ColumnLayout {

            anchors.fill:
                parent

            anchors.margins:
                16

            spacing:
                10


            // ---------------------------------------------------------
            // HEADER
            // ---------------------------------------------------------

            RowLayout {

                Layout.fillWidth:
                    true

                spacing:
                    10


                ColumnLayout {

                    Layout.fillWidth:
                        true

                    spacing:
                        1


                    PlasmaComponents.Label {

                        color: "#E6EDF3"

                        text:
                            "EURO INFO"

                        font.bold:
                            true

                        font.pixelSize:
                            17
                    }


                    PlasmaComponents.Label {

                        color: "#E6EDF3"

                        text:
                            root.statusText

                        opacity:
                            0.8

                        font.pixelSize:
                            10

                        elide:
                            Text.ElideRight

                        Layout.fillWidth:
                            true
                    }
                }


                Controls.ToolButton {

                    text:
                        root.loading
                        ? "…"
                        : "↻"

                    font.pixelSize:
                        18

                    enabled:
                        !root.loading

                    onClicked:
                        root.refresh()

                    Controls.ToolTip.visible:
                        hovered

                    Controls.ToolTip.text:
                        "Refresh now"
                }
            }


            // ---------------------------------------------------------
            // FILTERS
            // ---------------------------------------------------------

            RowLayout {

                Layout.fillWidth:
                    true

                spacing:
                    6


                Repeater {

                    model: [
                        "ALL",
                        "POLITICS",
                        "ECONOMY",
                        "TECHNOLOGY",
                        "SECURITY"
                    ]


                    delegate:
                        Controls.Button {

                            text:
                                modelData

                            checkable:
                                true

                            checked:
                                root.activeFilter ===
                                modelData

                            font.pixelSize:
                                9

                            Layout.fillWidth:
                                true

                            onClicked:
                                root.activeFilter =
                                    modelData
                        }
                }
            }


            // ---------------------------------------------------------
            // SEARCH
            // ---------------------------------------------------------

            Controls.TextField {

                Layout.fillWidth:
                    true

                placeholderText:
                    "Search stories…"

                text:
                    root.searchText

                onTextChanged:
                    root.searchText = text

            }


            // ---------------------------------------------------------
            // WEATHER HEADER
            // ---------------------------------------------------------

            PlasmaComponents.Label {

                        color: "#E6EDF3"

                text:
                    "WEATHER"

                font.bold:
                    true

                font.pixelSize:
                    10

                opacity:
                    0.8

                Layout.topMargin:
                    2
            }


            // ---------------------------------------------------------
            // WEATHER
            // ---------------------------------------------------------

            Flickable {

                Layout.fillWidth:
                    true

                Layout.preferredHeight:
                    82

                contentWidth:
                    weatherRow.width

                clip:
                    true

                boundsBehavior:
                    Flickable.StopAtBounds


                Row {

                    id:
                        weatherRow

                    spacing:
                        8


                    Repeater {

                        model:
                            Object.keys(root.weather)


                        delegate:
                            Rectangle {

                                width:
                                    118

                                height:
                                    76

                                radius:
                                    12

                                color:
                                    Qt.rgba(
                                        1,
                                        1,
                                        1,
                                        0.045
                                    )

                                border.width:
                                    1

                                border.color:
                                    Qt.rgba(
                                        1,
                                        1,
                                        1,
                                        0.06
                                    )


                                property var cityData:
                                    root.weather[
                                        modelData
                                    ]


                                Column {

                                    anchors.fill:
                                        parent

                                    anchors.margins:
                                        9

                                    spacing:
                                        2


                                    PlasmaComponents.Label {

                        color: "#E6EDF3"

                                        text:
                                            modelData

                                        font.bold:
                                            true

                                        font.pixelSize:
                                            10

                                        elide:
                                            Text.ElideRight

                                        width:
                                            parent.width
                                    }


                                    PlasmaComponents.Label {

                        color: "#E6EDF3"

                                        text:
                                            cityData.temperature !== undefined
                                            ? cityData.temperature + "°C"
                                            : "—"

                                        font.bold:
                                            true

                                        font.pixelSize:
                                            20
                                    }


                                    PlasmaComponents.Label {

                        color: "#E6EDF3"

                                        text:
                                            cityData.description ||
                                            cityData.condition ||
                                            ""

                                        opacity:
                                            0.8

                                        font.pixelSize:
                                            9

                                        elide:
                                            Text.ElideRight

                                        width:
                                            parent.width
                                    }
                                }
                            }
                    }
                }
            }


            // ---------------------------------------------------------
            // NEWS HEADER
            // ---------------------------------------------------------

            RowLayout {

                Layout.fillWidth:
                    true


                PlasmaComponents.Label {

                        color: "#E6EDF3"

                    text:
                        "LATEST STORIES"

                    font.bold:
                        true

                    font.pixelSize:
                        10

                    opacity:
                        0.8
                }


                Item {
                    Layout.fillWidth:
                        true
                }


                PlasmaComponents.Label {

                        color: "#E6EDF3"

                    text:
                        root.visibleArticles().length +
                        " stories"

                    opacity:
                        0.8

                    font.pixelSize:
                        10
                }
            }


            // ---------------------------------------------------------
            // NEWS LIST
            // ---------------------------------------------------------

            ListView {

                id:
                    storyList

                Layout.fillWidth:
                    true

                Layout.fillHeight:
                    true

                clip:
                    true

                spacing:
                    8

                boundsBehavior:
                    Flickable.StopAtBounds

                model:
                    root.visibleArticles()


                delegate:
                    Rectangle {

                        width:
                            storyList.width

                        height:
                            112

                        radius:
                            13

                        color:
                            Qt.rgba(
                                1,
                                1,
                                1,
                                0.045
                            )

                        border.width:
                            1

                        border.color:
                            Qt.rgba(
                                1,
                                1,
                                1,
                                0.055
                            )


                        RowLayout {

                            anchors.fill:
                                parent

                            anchors.margins:
                                9

                            spacing:
                                10


                            // -------------------------------------------------
                            // STORY IMAGE
                            // -------------------------------------------------

                            Rectangle {

                                Layout.preferredWidth:
                                    126

                                Layout.fillHeight:
                                    true

                                radius:
                                    9

                                clip:
                                    true

                                color:
                                    Qt.rgba(
                                        1,
                                        1,
                                        1,
                                        0.04
                                    )


                                Image {

                                    id:
                                        storyImage

                                    anchors.fill:
                                        parent

                                    source:
                                        modelData.image_url ||
                                        ""

                                    fillMode:
                                        Image.PreserveAspectCrop

                                    asynchronous:
                                        true

                                    cache:
                                        true

                                    visible:
                                        status === Image.Ready
                                }


                                PlasmaComponents.Label {

                        color: "#E6EDF3"

                                    anchors.centerIn:
                                        parent

                                    text:
                                        "🌍"

                                    font.pixelSize:
                                        25

                                    opacity:
                                        0.25

                                    visible:
                                        storyImage.status !==
                                        Image.Ready
                                }
                            }


                            // -------------------------------------------------
                            // STORY TEXT
                            // -------------------------------------------------

                            ColumnLayout {

                                Layout.fillWidth:
                                    true

                                Layout.fillHeight:
                                    true

                                spacing:
                                    4


                                PlasmaComponents.Label {

                        color: "#E6EDF3"

                                    text:
                                        (
                                            modelData.source ||
                                            "Unknown"
                                        ) +
                                        "  •  " +
                                        (
                                            modelData.category ||
                                            "GENERAL"
                                        )

                                    font.bold:
                                        true

                                    font.pixelSize:
                                        9

                                    opacity:
                                        0.8

                                    Layout.fillWidth:
                                        true

                                    elide:
                                        Text.ElideRight
                                }


                                PlasmaComponents.Label {

                        color: "#E6EDF3"

                                    text:
                                        modelData.title ||
                                        "Untitled"

                                    font.bold:
                                        true

                                    font.pixelSize:
                                        12

                                    Layout.fillWidth:
                                        true

                                    Layout.fillHeight:
                                        true

                                    maximumLineCount:
                                        3

                                    wrapMode:
                                        Text.WordWrap

                                    elide:
                                        Text.ElideRight
                                }


                                PlasmaComponents.Label {

                        color: "#E6EDF3"

                                    text:
                                        modelData.published ||
                                        ""

                                    font.pixelSize:
                                        9

                                    opacity:
                                        0.8

                                    Layout.fillWidth:
                                        true

                                    elide:
                                        Text.ElideRight
                                }
                            }
                        }


                        // -------------------------------------------------
                        // CLICK → ORIGINAL ARTICLE
                        // -------------------------------------------------

                        MouseArea {

                            anchors.fill:
                                parent

                            cursorShape:
                                Qt.PointingHandCursor

                            onClicked:
                                root.openArticle(
                                    modelData.link
                                )
                        }
                    }


                // Explicit scrollbar.
                // Do NOT use ScrollBar.vertical attached syntax here:
                // the Controls namespace alias can produce
                // "Non-existent attached object" on Plasma/Qt builds.

                Controls.ScrollBar {

                    id:
                        verticalScrollBar

                    parent:
                        storyList

                    anchors.top:
                        storyList.top

                    anchors.bottom:
                        storyList.bottom

                    anchors.right:
                        storyList.right

                    policy:
                        Controls.ScrollBar.AsNeeded

                    orientation: Qt.Vertical
                    size: Math.min(1, storyList.height / Math.max(1, storyList.contentHeight))
                    position: storyList.contentY / Math.max(1, storyList.contentHeight)
                    active: storyList.movingVertically || hovered || pressed
                    visible: size < 1
                    onPositionChanged: {
                        if (pressed)
                            storyList.contentY = position * storyList.contentHeight
                    }
                }


                PlasmaComponents.Label {

                        color: "#E6EDF3"

                    anchors.centerIn:
                        parent

                    text:
                        root.loading
                        ? "Loading Euro Info…"
                        : "No stories found"

                    opacity:
                        0.8

                    visible:
                        storyList.count === 0
                }
            }
        }
    }
}
