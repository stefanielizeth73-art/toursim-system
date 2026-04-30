(function () {
    function ready(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback);
            return;
        }
        callback();
    }

    function htmlEscape(value) {
        return String(value || "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll("\"", "&quot;");
    }

    ready(function () {
        if (!window.L || !window.routeMapData) {
            return;
        }

        const data = window.routeMapData;
        const graph = data.graph || {};
        const nodes = graph.nodes || [];
        const edges = graph.edges || [];
        const mapEl = document.getElementById("routeMap");
        const form = document.getElementById("routePlanner");
        const startSelect = document.getElementById("startNode");
        const endSelect = document.getElementById("endNode");
        const routeTypeSelect = document.getElementById("routeType");
        const multiPanel = document.getElementById("multiTargetPanel");

        if (!mapEl || !nodes.length) {
            return;
        }

        const campusBoundsData = graph.campus_bounds && graph.campus_bounds.length === 2
            ? graph.campus_bounds
            : graph.bounds && graph.bounds.length === 2
                ? graph.bounds
                : null;
        const campusBounds = campusBoundsData ? L.latLngBounds(campusBoundsData) : null;
        const center = graph.center && graph.center.length === 2
            ? graph.center
            : [nodes[0].lat, nodes[0].lon];

        const map = L.map(mapEl, {
            zoomControl: true,
            minZoom: 16,
            maxBounds: campusBounds,
            maxBoundsViscosity: 0.92,
            scrollWheelZoom: true,
            preferCanvas: true
        }).setView(center, 16);

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 20,
            attribution: "&copy; OpenStreetMap contributors"
        }).addTo(map);

        const roadLayer = L.layerGroup().addTo(map);
        const roadNodeLayer = L.layerGroup();
        const poiLayer = L.layerGroup().addTo(map);
        const routeLayer = L.layerGroup().addTo(map);

        edges.forEach(function (edge) {
            if (!edge.geometry || edge.geometry.length < 2) {
                return;
            }
            const connector = edge.source === "manual_poi_connector" || edge.source === "manual_component_connector";
            L.polyline(edge.geometry, {
                color: connector ? "#8bb2c7" : "#789ab4",
                weight: connector ? 2 : 2.6,
                opacity: connector ? 0.34 : 0.48,
                dashArray: connector ? "3 8" : null,
                lineCap: "round",
                lineJoin: "round",
                className: connector ? "campus-connector-line" : "campus-road-line"
            }).addTo(roadLayer);
        });

        const routeGeometry = data.multiResult && data.multiResult.geometry && data.multiResult.geometry.length
            ? data.multiResult.geometry
            : data.result && data.result.geometry
                ? data.result.geometry
                : [];

        if (routeGeometry.length) {
            const routeLine = L.polyline(routeGeometry, {
                color: "#ffd166",
                weight: 8,
                opacity: 0.98,
                lineCap: "round",
                lineJoin: "round",
                className: "leaflet-route-line"
            }).addTo(routeLayer);
            L.polyline(routeGeometry, {
                color: "#245d7a",
                weight: 3,
                opacity: 0.92,
                dashArray: "2 16",
                lineCap: "round",
                className: "leaflet-route-dashes"
            }).addTo(routeLayer);
            window.setTimeout(function () {
                map.fitBounds(routeLine.getBounds(), { padding: [36, 36], maxZoom: 17 });
            }, 260);
        }

        function markerColor(node) {
            return {
                gate: "#ffd166",
                building: "#79c7f2",
                facility: "#6ee7a8",
                landmark: "#f7a6bc",
                road: "#91aabd"
            }[node.kind] || "#d7e4f2";
        }

        function setSelectValue(select, value) {
            if (!select || !value) {
                return;
            }
            select.value = value;
            select.dispatchEvent(new Event("change", { bubbles: true }));
        }

        function popupHtml(node) {
            if (node.selectable === false || node.kind === "road") {
                return `<strong>${htmlEscape(node.name)}</strong><br>${htmlEscape(node.category)}`;
            }
            return (
                `<strong>${htmlEscape(node.name)}</strong><br>${htmlEscape(node.category)}<br>` +
                `<button type="button" data-node-action="start" data-node-id="${htmlEscape(node.id)}">设为起点</button> ` +
                `<button type="button" data-node-action="end" data-node-id="${htmlEscape(node.id)}">设为终点</button>`
            );
        }

        nodes.forEach(function (node) {
            if (node.lat == null || node.lon == null) {
                return;
            }
            const isRoad = node.selectable === false || node.kind === "road";
            const marker = L.circleMarker([node.lat, node.lon], {
                radius: isRoad ? 2.4 : node.kind === "gate" ? 7.5 : 5.8,
                color: isRoad ? "rgba(20, 42, 60, 0.8)" : "#152335",
                weight: isRoad ? 1 : 2.5,
                fillColor: markerColor(node),
                fillOpacity: isRoad ? 0.46 : 0.96
            });

            marker.bindTooltip(node.name, {
                direction: "top",
                offset: [0, -8],
                opacity: 0.94,
                permanent: !isRoad && ["gate", "building", "facility"].includes(node.kind)
            });
            marker.bindPopup(popupHtml(node));

            if (isRoad) {
                marker.addTo(roadNodeLayer);
            } else {
                marker.addTo(poiLayer);
            }
        });

        map.on("popupopen", function (event) {
            const container = event.popup.getElement();
            if (!container) {
                return;
            }
            container.querySelectorAll("[data-node-action]").forEach(function (button) {
                button.addEventListener("click", function () {
                    const nodeId = button.getAttribute("data-node-id");
                    const action = button.getAttribute("data-node-action");
                    setSelectValue(action === "start" ? startSelect : endSelect, nodeId);
                    map.closePopup();
                });
            });
        });

        function fitCampusBounds() {
            map.invalidateSize();
            if (campusBounds) {
                map.fitBounds(campusBounds, { padding: [8, 8], maxZoom: 16 });
            }
        }

        function syncMode() {
            const isMulti = routeTypeSelect && routeTypeSelect.value === "multi";
            if (multiPanel) {
                multiPanel.classList.toggle("is-active", isMulti);
            }
            if (endSelect) {
                endSelect.disabled = isMulti;
            }
        }

        if (routeTypeSelect) {
            routeTypeSelect.addEventListener("change", syncMode);
            syncMode();
        }

        if (form) {
            form.addEventListener("change", function (event) {
                if (event.target.matches("select, input[type='checkbox']")) {
                    window.clearTimeout(form._routeSubmitTimer);
                    form._routeSubmitTimer = window.setTimeout(function () {
                        form.requestSubmit();
                    }, 280);
                }
            });
        }

        if (!routeGeometry.length) {
            fitCampusBounds();
        }

        window.addEventListener("resize", function () {
            map.invalidateSize();
        });

        window.setTimeout(function () {
            map.invalidateSize();
            if (routeGeometry.length) {
                map.fitBounds(L.latLngBounds(routeGeometry), { padding: [36, 36], maxZoom: 17 });
            } else {
                fitCampusBounds();
            }
        }, 380);
    });
}());
