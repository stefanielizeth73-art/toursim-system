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

    function haversine(lat1, lon1, lat2, lon2) {
        const radius = 6371000;
        const toRad = Math.PI / 180;
        const phi1 = lat1 * toRad;
        const phi2 = lat2 * toRad;
        const dPhi = (lat2 - lat1) * toRad;
        const dLambda = (lon2 - lon1) * toRad;
        const a = Math.sin(dPhi / 2) ** 2
            + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
        return 2 * radius * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    ready(async function () {
        if (!window.routeMapData) {
            return;
        }

        const data = window.routeMapData;
        const collectMode = Boolean(data.amap && data.amap.collectMode);
        const foodPickMode = Boolean(data.amap && data.amap.foodPickMode);
        const transportMode = String((data.state && data.state.transport) || data.transport || "walk");
        const mapEl = document.getElementById("routeMap");
        const form = document.getElementById("routePlanner");
        const startSelect = document.getElementById("startNode");
        const endSelect = document.getElementById("endNode");
        const showRoadNetworkToggle = document.getElementById("showRoadNetwork");
        const showFacilityLayerToggle = document.getElementById("showFacilityLayer");
        const routeTypeSelect = document.getElementById("routeType");
        const multiPanel = document.getElementById("multiTargetPanel");
        const poiSearch = document.getElementById("routePoiSearch");
        const selectedTargetsEl = document.getElementById("selectedTargets");
        const clearTargetsButton = document.getElementById("clearTargets");
        const targetInputsEl = document.getElementById("targetInputs");
        const initialTargets = (data.state && data.state.targets) || [];
        const selectedTargets = new Set(initialTargets.map(function (value) { return String(value); }));
        const targetOrder = (data.multiResult && data.multiResult.order && data.multiResult.order.length
            ? data.multiResult.order
            : initialTargets).map(function (value) { return String(value); });
        const maxTargets = 8;
        const routeClickRadiusMeters = 50;
        const endpointSearchLimit = 6;
        targetOrder.forEach(function (targetId) { selectedTargets.add(targetId); });

        if (!mapEl) {
            return;
        }

        const mapStage = mapEl.closest(".map-stage") || mapEl.parentElement || mapEl;
        let mapStatusEl = null;
        function showMapStatus(message) {
            if (!mapStatusEl) {
                mapStatusEl = document.createElement("div");
                mapStatusEl.className = "amap-empty-state route-map-status";
                mapStage.appendChild(mapStatusEl);
            }
            mapStatusEl.textContent = message;
        }

        function clearMapStatus() {
            if (mapStatusEl) {
                mapStatusEl.remove();
                mapStatusEl = null;
            }
            mapEl.replaceChildren();
        }

        if (!window.AMap || !data.amap || !data.amap.enabled) {
            showMapStatus("高德地图未加载。请设置 AMAP_JS_KEY 和 AMAP_SECURITY_JS_CODE 后重启应用。");
            return;
        }

        if (data.graphUrl && !data.graph) {
            try {
                const response = await fetch(data.graphUrl, { cache: "force-cache" });
                if (!response.ok) {
                    throw new Error("route graph request failed");
                }
                const payload = await response.json();
                data.graph = payload.graph || {};
                data.facilities = payload.facilities || [];
            } catch (error) {
                showMapStatus("路线图数据加载失败，请刷新页面重试。");
                return;
            }
        }

        const graph = data.graph || {};
        const nodes = graph.nodes || [];
        const edges = graph.edges || [];
        const facilities = data.facilities || [];

        function nodeLngLat(node) {
            if (node.amap_lng != null && node.amap_lat != null) {
                return [Number(node.amap_lng), Number(node.amap_lat)];
            }
            if (node.lon != null && node.lat != null) {
                return [Number(node.lon), Number(node.lat)];
            }
            return null;
        }

        function routePath(points) {
            return (points || [])
                .filter(function (point) { return point && point.length >= 2; })
                .map(function (point) { return [Number(point[0]), Number(point[1])]; });
        }

        function fallbackPath(points) {
            return (points || [])
                .filter(function (point) { return point && point.length >= 2; })
                .map(function (point) { return [Number(point[1]), Number(point[0])]; });
        }

        function graphPath(edge) {
            return edge.amap_geometry && edge.amap_geometry.length
                ? routePath(edge.amap_geometry)
                : fallbackPath(edge.geometry);
        }

        function facilityLngLat(facility) {
            if (facility.amap_lng != null && facility.amap_lat != null) {
                return [Number(facility.amap_lng), Number(facility.amap_lat)];
            }
            if (facility.lon != null && facility.lat != null) {
                return [Number(facility.lon), Number(facility.lat)];
            }
            return null;
        }

        function facilityDisplayName(facility) {
            if (!facility) {
                return "场所";
            }
            const name = String(facility.name || facility.category || facility.type || facility.id || "").trim();
            return name || "场所";
        }

        function facilityTypeLabel(facility) {
            if (!facility) {
                return "场所";
            }
            const label = String(facility.type || facility.category || "").trim();
            return label || "场所";
        }

        function facilityMarkerContent(facility, extraClass) {
            const displayName = facilityDisplayName(facility);
            const typeLabel = facilityTypeLabel(facility);
            return (
                `<div class="facility-map-marker ${extraClass || ""}">` +
                "<span class=\"facility-map-dot\"></span>" +
                `<div class="facility-map-label"><strong>${htmlEscape(displayName)}</strong><small>${htmlEscape(typeLabel)}</small></div>` +
                "</div>"
            );
        }

        function routePointMarkerContent(node, extraClass) {
            return (
                `<div class="route-point-map-marker ${markerClass(node)} ${extraClass || ""}">` +
                "<span class=\"route-point-map-dot\"></span>" +
                `<span class="route-point-map-label">${htmlEscape(node.name)}</span>` +
                "</div>"
            );
        }

        function centerLngLat() {
            if (graph.amap_center && graph.amap_center.length === 2) {
                return [Number(graph.amap_center[0]), Number(graph.amap_center[1])];
            }
            if (graph.center && graph.center.length === 2) {
                return [Number(graph.center[1]), Number(graph.center[0])];
            }
            return nodes.length ? nodeLngLat(nodes[0]) : [118.3099666, 24.6095855];
        }

        function campusBounds() {
            const bounds = graph.amap_bounds && graph.amap_bounds.length === 2
                ? graph.amap_bounds
                : graph.campus_bounds && graph.campus_bounds.length === 2
                    ? [[graph.campus_bounds[0][1], graph.campus_bounds[0][0]], [graph.campus_bounds[1][1], graph.campus_bounds[1][0]]]
                    : null;
            if (!bounds) {
                return null;
            }
            return new AMap.Bounds(bounds[0], bounds[1]);
        }

        function expandedCampusBounds(ratio) {
            const bounds = graph.amap_bounds && graph.amap_bounds.length === 2
                ? graph.amap_bounds
                : graph.campus_bounds && graph.campus_bounds.length === 2
                    ? [[graph.campus_bounds[0][1], graph.campus_bounds[0][0]], [graph.campus_bounds[1][1], graph.campus_bounds[1][0]]]
                    : null;
            if (!bounds) {
                return null;
            }
            const west = Number(bounds[0][0]);
            const south = Number(bounds[0][1]);
            const east = Number(bounds[1][0]);
            const north = Number(bounds[1][1]);
            const lngPad = Math.max((east - west) * ratio, 0.0012);
            const latPad = Math.max((north - south) * ratio, 0.0009);
            return new AMap.Bounds([west - lngPad, south - latPad], [east + lngPad, north + latPad]);
        }

        const mapStyleOptions = {
            color: "amap://styles/normal",
            gray: "amap://styles/whitesmoke"
        };
        const savedMapStyle = window.localStorage && window.localStorage.getItem("xmu_route_map_style");
        let currentMapStyle = mapStyleOptions[savedMapStyle] ? savedMapStyle : "color";
        const campusLimit = campusBounds();
        const expandedCampusLimit = expandedCampusBounds(0.08);
        const map = new AMap.Map(mapEl, {
            viewMode: "2D",
            center: centerLngLat(),
            zoom: 17,
            zooms: [16, 19],
            resizeEnable: true,
            mapStyle: mapStyleOptions[currentMapStyle],
            features: ["bg", "road", "building", "point"],
            showIndoorMap: false,
            pitchEnable: false,
            rotateEnable: false
        });

        map.addControl(new AMap.Scale({ position: "LB" }));
        if (campusLimit && !collectMode) {
            map.setLimitBounds(expandedCampusLimit || campusLimit);
            map.setBounds(campusLimit);
        } else if (campusLimit) {
            // Collection mode must stay free of electronic fences so edge-area road capture
            // does not fight the user's drag gesture.
            map.setBounds(campusLimit);
        }

        function setupBasemapSwitcher() {
            const switcher = document.createElement("div");
            switcher.className = "route-basemap-switcher";
            switcher.innerHTML = (
                "<button type=\"button\" data-map-style=\"color\">彩色</button>" +
                "<button type=\"button\" data-map-style=\"gray\">浅灰</button>"
            );
            function syncButtons() {
                switcher.querySelectorAll("[data-map-style]").forEach(function (button) {
                    button.classList.toggle("is-active", button.getAttribute("data-map-style") === currentMapStyle);
                });
            }
            switcher.addEventListener("click", function (event) {
                const button = event.target.closest("[data-map-style]");
                if (!button) {
                    return;
                }
                const nextStyle = button.getAttribute("data-map-style");
                if (!mapStyleOptions[nextStyle]) {
                    return;
                }
                currentMapStyle = nextStyle;
                map.setMapStyle(mapStyleOptions[currentMapStyle]);
                if (window.localStorage) {
                    window.localStorage.setItem("xmu_route_map_style", currentMapStyle);
                }
                syncButtons();
            });
            syncButtons();
            mapEl.parentElement.appendChild(switcher);
        }

        setupBasemapSwitcher();

        const roadOverlays = [];
        const routeOverlays = [];
        const poiMarkers = [];
        let roadOverlaysVisible = false;
        function removeOverlayList(overlays) {
            overlays.forEach(function (overlay) {
                if (overlay) {
                    map.remove(overlay);
                }
            });
            overlays.length = 0;
        }

        function syncLayerToggleButton(button, visible) {
            if (!button) {
                return;
            }
            button.classList.toggle("is-active", visible);
            button.setAttribute("aria-pressed", visible ? "true" : "false");
            const stateEl = button.querySelector(".route-layer-toggle__state");
            if (stateEl) {
                stateEl.textContent = visible ? "开" : "关";
            }
        }

        function setRoadOverlayVisible(visible) {
            if (collectMode || !roadOverlays.length || roadOverlaysVisible === visible) {
                return;
            }
            roadOverlaysVisible = visible;
            if (visible) {
                map.add(roadOverlays);
            } else {
                roadOverlays.forEach(function (overlay) {
                    map.remove(overlay);
                });
            }
        }

        syncLayerToggleButton(showRoadNetworkToggle, false);
        syncLayerToggleButton(showFacilityLayerToggle, false);
        const nodeById = new Map(nodes.map(function (node) { return [String(node.id), node]; }));
        const selectableNodes = nodes.filter(function (node) {
            return node.selectable !== false && node.kind !== "road" && nodeLngLat(node);
        });
        const infoWindow = new AMap.InfoWindow({
            isCustom: true,
            offset: new AMap.Pixel(0, -22),
            closeWhenClickMap: true
        });

        if (!collectMode) {
            const roadDisplayEdges = Array.isArray(graph.road_display_edges) && graph.road_display_edges.length
                ? graph.road_display_edges
                : edges;
            roadDisplayEdges.forEach(function (edge) {
                const path = graphPath(edge);
                if (path.length < 2) {
                    return;
                }
                const connector = edge.source === "manual_poi_connector" || edge.source === "manual_component_connector";
                roadOverlays.push(new AMap.Polyline({
                    path,
                    strokeColor: connector ? "#87aebd" : "#5f91a0",
                    strokeWeight: connector ? 2 : 2.4,
                    strokeOpacity: connector ? 0.28 : 0.38,
                    strokeStyle: connector ? "dashed" : "solid",
                    lineJoin: "round",
                    lineCap: "round",
                    zIndex: connector ? 18 : 20
                }));
            });
        }
        if (showRoadNetworkToggle) {
            showRoadNetworkToggle.addEventListener("click", function () {
                const nextVisible = !roadOverlaysVisible;
                setRoadOverlayVisible(nextVisible);
                syncLayerToggleButton(showRoadNetworkToggle, nextVisible);
            });
        }

        const routeGeometry = data.multiResult && data.multiResult.amap_geometry && data.multiResult.amap_geometry.length
            ? routePath(data.multiResult.amap_geometry)
            : data.result && data.result.amap_geometry && data.result.amap_geometry.length
                ? routePath(data.result.amap_geometry)
                : data.multiResult && data.multiResult.geometry && data.multiResult.geometry.length
                    ? fallbackPath(data.multiResult.geometry)
                    : data.result && data.result.geometry
                        ? fallbackPath(data.result.geometry)
                        : [];

        const routePalettes = {
            walk: {
                outline: "#3a2210",
                halo: "#f08a2f",
                core: "#fff4df"
            },
            bike: {
                outline: "#0b2442",
                halo: "#4f7fb8",
                core: "#eef6ff"
            }
        };
        let routeArrowDrawn = false;
        function routeEdgePath(edge) {
            if (edge && edge.amap_geometry && edge.amap_geometry.length) {
                return routePath(edge.amap_geometry);
            }
            if (edge && edge.geometry && edge.geometry.length) {
                return fallbackPath(edge.geometry);
            }
            return [];
        }

        function routeResultEdges() {
            if (data.multiResult && Array.isArray(data.multiResult.segments)) {
                return data.multiResult.segments.reduce(function (items, segment) {
                    return items.concat(segment && Array.isArray(segment.edges) ? segment.edges : []);
                }, []);
            }
            return data.result && Array.isArray(data.result.edges) ? data.result.edges : [];
        }

        function routeModeForEdge(edge) {
            if (transportMode === "bike") {
                return "bike";
            }
            if (transportMode === "mixed") {
                return edge && edge.bike ? "bike" : "walk";
            }
            return "walk";
        }

        function routePathDistance(path) {
            let total = 0;
            for (let index = 1; index < path.length; index += 1) {
                total += haversine(
                    path[index - 1][1],
                    path[index - 1][0],
                    path[index][1],
                    path[index][0]
                );
            }
            return total;
        }

        function routeSampleAtFraction(path, fraction) {
            if (!path || path.length < 2) {
                return null;
            }
            const totalDistance = routePathDistance(path);
            if (!Number.isFinite(totalDistance) || totalDistance <= 0) {
                return null;
            }
            const targetDistance = totalDistance * Math.max(0.05, Math.min(0.95, fraction));
            let traversed = 0;
            for (let index = 1; index < path.length; index += 1) {
                const from = path[index - 1];
                const to = path[index];
                const segmentDistance = haversine(from[1], from[0], to[1], to[0]);
                if (traversed + segmentDistance >= targetDistance) {
                    const ratio = segmentDistance > 0 ? (targetDistance - traversed) / segmentDistance : 0;
                    const lng = from[0] + (to[0] - from[0]) * ratio;
                    const lat = from[1] + (to[1] - from[1]) * ratio;
                    const angle = Math.atan2(to[1] - from[1], to[0] - from[0]) * 180 / Math.PI;
                    return {
                        point: [lng, lat],
                        angle
                    };
                }
                traversed += segmentDistance;
            }
            const from = path[path.length - 2];
            const to = path[path.length - 1];
            return {
                point: [to[0], to[1]],
                angle: Math.atan2(to[1] - from[1], to[0] - from[0]) * 180 / Math.PI
            };
        }

        function addRouteArrow(path, mode, fraction) {
            const sample = routeSampleAtFraction(path, fraction);
            if (!sample) {
                return;
            }
            routeOverlays.push(new AMap.Marker({
                position: sample.point,
                content: (
                    `<div class="route-flow-arrow route-flow-arrow--${mode}" ` +
                    `style="transform: translate(-50%, -50%) rotate(${sample.angle}deg);" aria-hidden="true">` +
                    `<span class="route-flow-arrow__blade"></span>` +
                    `<span class="route-flow-arrow__stem"></span>` +
                    `</div>`
                ),
                anchor: "center",
                zIndex: 93
            }));
        }

        function addRouteArrows(path, mode) {
            if (routeArrowDrawn || !path || path.length < 2) {
                return;
            }
            const length = routePathDistance(path);
            if (!Number.isFinite(length) || length < 520) {
                return;
            }
            routeArrowDrawn = true;
            addRouteArrow(path, mode, 0.62);
        }

        function addRoutePolyline(path, mode) {
            if (!path || path.length < 2) {
                return;
            }
            const routePalette = routePalettes[mode] || routePalettes.walk;
            routeOverlays.push(new AMap.Polyline({
                path,
                strokeColor: routePalette.halo,
                strokeWeight: 7,
                strokeOpacity: 0.96,
                lineJoin: "round",
                lineCap: "round",
                showDir: false,
                zIndex: 90
            }));
        }

        if (routeGeometry.length) {
            if (transportMode === "mixed") {
                const routeEdges = routeResultEdges();
                if (routeEdges.length) {
                    routeEdges.forEach(function (edge) {
                        addRoutePolyline(routeEdgePath(edge), routeModeForEdge(edge));
                    });
                } else {
                    addRoutePolyline(routeGeometry, "walk");
                }
                if (!routeOverlays.length) {
                    addRoutePolyline(routeGeometry, "walk");
                }
            } else {
                addRoutePolyline(routeGeometry, transportMode === "bike" ? "bike" : "walk");
            }
            map.add(routeOverlays);
            window.setTimeout(function () {
                map.setFitView(routeOverlays, false, [50, 50, 50, 50], 18);
            }, 240);
        }

        function markerClass(node) {
            return {
                gate: "is-gate",
                building: "is-building",
                facility: "is-facility",
                landmark: "is-landmark"
            }[node.kind] || "is-default";
        }

        function setSelectValue(select, value) {
            if (!select || value === undefined) {
                return;
            }
            select.value = value;
            select.dispatchEvent(new Event("change", { bubbles: true }));
        }

        function submitPlanner() {
            if (!form) {
                return;
            }
            window.clearTimeout(form._routeSubmitTimer);
            form._routeSubmitTimer = window.setTimeout(function () {
                form.requestSubmit();
            }, 120);
        }

        function openFoodsFromOrigin(nodeId) {
            if (!nodeId) {
                return;
            }
            const state = data.state || {};
            const placeId = state.returnPlaceId || state.placeId || graph.place_id || "xmu_manual";
            if (state.returnTo === "food_detail" && state.returnFoodKey) {
                const params = new URLSearchParams();
                params.set("place_id", placeId);
                params.set("origin_node", nodeId);
                window.location.href = `/food/${encodeURIComponent(state.returnFoodKey)}?${params.toString()}`;
                return;
            }
            const params = new URLSearchParams();
            params.set("place_id", placeId);
            params.set("origin_node", nodeId);
            params.set("sort_by", "distance_asc");
            window.location.href = `/foods?${params.toString()}`;
        }

        function setRouteMode(mode) {
            if (!routeTypeSelect) {
                return;
            }
            routeTypeSelect.value = mode;
            routeTypeSelect.dispatchEvent(new Event("change", { bubbles: true }));
        }

        function ensureWaypointRouteMode() {
            if (!routeTypeSelect) {
                return;
            }
            const currentMode = routeTypeSelect.value;
            if (currentMode === "multi" || currentMode === "round_trip") {
                return;
            }
            setRouteMode("multi");
        }

        function targetDisplayName(targetId) {
            const node = nodeById.get(targetId);
            return node ? node.name : targetId;
        }

        function currentStartId() {
            return startSelect && startSelect.value ? String(startSelect.value) : "";
        }

        function currentEndId() {
            return endSelect && endSelect.value ? String(endSelect.value) : "";
        }

        function isEndpointId(nodeId) {
            const id = String(nodeId || "");
            return id && (id === currentStartId() || id === currentEndId());
        }

        function ensureTargetOrder() {
            selectedTargets.forEach(function (targetId) {
                if (!targetOrder.includes(targetId)) {
                    targetOrder.push(targetId);
                }
            });
        }

        function normalizedTargetItems() {
            const startId = currentStartId();
            const endId = currentEndId();
            if (startId) {
                selectedTargets.delete(startId);
            }
            if (endId) {
                selectedTargets.delete(endId);
            }
            for (let index = targetOrder.length - 1; index >= 0; index -= 1) {
                const targetId = targetOrder[index];
                if (!selectedTargets.has(targetId) || targetId === startId || targetId === endId) {
                    targetOrder.splice(index, 1);
                }
            }
            ensureTargetOrder();
            return targetOrder
                .filter(function (targetId) { return selectedTargets.has(targetId) && !isEndpointId(targetId); })
                .map(function (targetId) {
                    return {
                        id: targetId,
                        name: targetDisplayName(targetId)
                    };
                });
        }

        function syncTargetInputs(items) {
            if (!targetInputsEl) {
                return;
            }
            targetInputsEl.innerHTML = "";
            items.forEach(function (item) {
                const input = document.createElement("input");
                input.type = "hidden";
                input.name = "targets";
                input.value = item.id;
                targetInputsEl.appendChild(input);
            });
        }

        function setTargetValue(nodeId, checked) {
            const targetId = String(nodeId || "");
            if (!targetId) {
                return false;
            }
            if (checked && isEndpointId(targetId)) {
                return false;
            }
            const alreadySelected = selectedTargets.has(targetId);
            if (checked && !alreadySelected && normalizedTargetItems().length >= maxTargets) {
                window.alert(`途经点最多 ${maxTargets} 个。`);
                return false;
            }
            if (checked) {
                selectedTargets.add(targetId);
                if (targetOrder.indexOf(targetId) === -1) {
                    targetOrder.push(targetId);
                }
            } else {
                selectedTargets.delete(targetId);
                const index = targetOrder.indexOf(targetId);
                if (index !== -1) {
                    targetOrder.splice(index, 1);
                }
            }
            refreshSelectedTargets();
            return true;
        }

        function refreshSelectedTargets() {
            const items = normalizedTargetItems();
            if (selectedTargetsEl) {
                selectedTargetsEl.innerHTML = items.length
                    ? items.map(function (item, index) {
                        return `<button type="button" class="target-chip" data-remove-target="${htmlEscape(item.id)}"><strong>${index + 1}</strong><em>${htmlEscape(item.name)}</em><span aria-hidden="true">x</span></button>`;
                    }).join("")
                    : "<span class=\"target-empty\">点击地图点位或搜索名称添加途经点</span>";
            }
            syncTargetInputs(items);
            if (clearTargetsButton) {
                clearTargetsButton.disabled = !currentStartId() && !currentEndId() && items.length === 0;
            }
            if (!collectMode && typeof redrawPlanningMarkers === "function") {
                redrawPlanningMarkers();
            }
        }

        function clearAllRoutePoints() {
            infoWindow.close();
            if (startSelect) {
                startSelect.value = "";
            }
            if (endSelect) {
                endSelect.value = "";
            }
            selectedTargets.clear();
            targetOrder.length = 0;
            refreshSelectedTargets();
            refreshEndpointSearchControls();
        }

        function setRouteEndpoint(kind, nodeId) {
            const targetSelect = kind === "start" ? startSelect : endSelect;
            if (!targetSelect) {
                return;
            }
            const id = String(nodeId || "");
            if (id) {
                selectedTargets.delete(id);
                const index = targetOrder.indexOf(id);
                if (index !== -1) {
                    targetOrder.splice(index, 1);
                }
                if (kind === "start" && endSelect && String(endSelect.value) === id) {
                    endSelect.value = "";
                }
                if (kind === "end" && startSelect && String(startSelect.value) === id) {
                    startSelect.value = "";
                }
            }
            setSelectValue(targetSelect, id);
            refreshSelectedTargets();
            refreshEndpointSearchControls();
        }

        const endpointSearchControls = [];

        function nodeSearchText(node) {
            return `${node.name || ""} ${node.category || ""} ${node.id || ""}`.toLowerCase();
        }

        function endpointMatches(query) {
            const normalized = String(query || "").trim().toLowerCase();
            const source = selectableNodes.slice();
            if (!normalized) {
                return source.slice(0, endpointSearchLimit);
            }
            const exact = [];
            const prefix = [];
            const contains = [];
            source.forEach(function (node) {
                const name = String(node.name || "").toLowerCase();
                const id = String(node.id || "").toLowerCase();
                const text = nodeSearchText(node);
                if (name === normalized || id === normalized) {
                    exact.push(node);
                } else if (name.startsWith(normalized)) {
                    prefix.push(node);
                } else if (text.includes(normalized)) {
                    contains.push(node);
                }
            });
            return exact.concat(prefix, contains).slice(0, endpointSearchLimit);
        }

        function endpointLabelFor(kind) {
            return kind === "start" ? "起点" : "终点";
        }

        function currentEndpointName(select) {
            const node = select && select.value ? nodeById.get(String(select.value)) : null;
            return node ? node.name : "";
        }

        function renderEndpointResults(control, query) {
            const matches = endpointMatches(query);
            control.results.innerHTML = matches.length
                ? matches.map(function (node) {
                    return (
                        `<button type="button" data-endpoint-result="${htmlEscape(node.id)}">` +
                        `<strong>${htmlEscape(node.name)}</strong>` +
                        `<small>${htmlEscape(node.category || node.kind || "")}</small>` +
                        "</button>"
                    );
                }).join("")
                : "<span class=\"endpoint-search-empty\">没有匹配地点</span>";
            control.root.classList.toggle("is-open", true);
        }

        function refreshEndpointSearchControls() {
            endpointSearchControls.forEach(function (control) {
                const name = currentEndpointName(control.select);
                control.chip.hidden = !name;
                control.chipName.textContent = name || endpointLabelFor(control.kind);
                control.input.placeholder = name ? "重新搜索地点" : `搜索${endpointLabelFor(control.kind)}`;
            });
        }

        function enhanceEndpointSearch(select, kind) {
            if (!select || collectMode) {
                return;
            }
            const label = select.closest("label");
            if (label) {
                label.classList.add("endpoint-search-field");
            }
            select.classList.add("endpoint-native-select");
            const root = document.createElement("div");
            root.className = "endpoint-search-control";
            root.innerHTML = (
                "<div class=\"endpoint-selected-chip\" hidden>" +
                `<span></span><button type="button" aria-label="清除${endpointLabelFor(kind)}">×</button>` +
                "</div>" +
                `<input type="search" class="endpoint-search-input" autocomplete="off" placeholder="搜索${endpointLabelFor(kind)}">` +
                "<div class=\"endpoint-search-results\" role=\"listbox\"></div>"
            );
            select.insertAdjacentElement("afterend", root);
            const control = {
                kind,
                select,
                root,
                input: root.querySelector(".endpoint-search-input"),
                results: root.querySelector(".endpoint-search-results"),
                chip: root.querySelector(".endpoint-selected-chip"),
                chipName: root.querySelector(".endpoint-selected-chip span")
            };
            endpointSearchControls.push(control);

            control.input.addEventListener("input", function () {
                renderEndpointResults(control, control.input.value);
            });
            control.input.addEventListener("focus", function () {
                renderEndpointResults(control, control.input.value);
            });
            control.results.addEventListener("click", function (event) {
                const button = event.target.closest("[data-endpoint-result]");
                if (!button) {
                    return;
                }
                setRouteEndpoint(kind, button.getAttribute("data-endpoint-result"));
                control.input.value = "";
                control.root.classList.remove("is-open");
                submitPlanner();
            });
            control.chip.querySelector("button").addEventListener("click", function () {
                setRouteEndpoint(kind, "");
                submitPlanner();
            });
        }

        function selectedWaypointCount() {
            return normalizedTargetItems().length;
        }

        enhanceEndpointSearch(startSelect, "start");
        enhanceEndpointSearch(endSelect, "end");
        refreshEndpointSearchControls();

        document.addEventListener("click", function (event) {
            endpointSearchControls.forEach(function (control) {
                if (!control.root.contains(event.target)) {
                    control.root.classList.remove("is-open");
                }
            });
        });

        function handleRoutePointRightClick(node, event) {
            if (collectMode) {
                return;
            }
            if (event && event.originEvent) {
                if (event.originEvent.preventDefault) {
                    event.originEvent.preventDefault();
                }
                if (event.originEvent.stopPropagation) {
                    event.originEvent.stopPropagation();
                }
            }
            const nodeId = String(node.id);
            const isStart = nodeId === currentStartId();
            const isEnd = nodeId === currentEndId();
            const isWaypoint = selectedTargets.has(nodeId);
            if (!isStart && !isEnd && !isWaypoint) {
                return;
            }
            if ((isStart || isEnd) && selectedWaypointCount() === 0) {
                clearAllRoutePoints();
                submitPlanner();
                return;
            }
            if (isStart && startSelect) {
                startSelect.value = "";
            } else if (isEnd && endSelect) {
                endSelect.value = "";
            } else {
                setTargetValue(nodeId, false);
            }
            refreshSelectedTargets();
            submitPlanner();
        }

        function handleRouteMapRightClick(event) {
            if (roadEditorActive) {
                return;
            }
            const lng = event.lnglat.getLng();
            const lat = event.lnglat.getLat();
            const closest = nearestSelectable(lng, lat);
            if (!closest || closest.distance > routeClickRadiusForZoom()) {
                return;
            }
            if (!shouldShowPlanningNode(closest.node, planningTargetInfo(closest.node.id))) {
                return;
            }
            handleRoutePointRightClick(closest.node, event);
        }
        function isIndoorBuildingNode(node) {
            const kind = String((node && node.kind) || "").trim();
            return ["building", "teaching", "library", "dorm", "canteen"].indexOf(kind) !== -1;
        }

        function openIndoorNavigation(node) {
            const params = new URLSearchParams();
            params.set("building_id", String(node.id || "demo_building"));
            params.set("building_name", String(node.name || "通用教学楼"));
            window.location.href = "/indoor?" + params.toString();
        }

        function popupContent(node) {
            const nodeId = String(node.id);
            const isEnd = endSelect && String(endSelect.value) === nodeId;
            const isTarget = selectedTargets.has(nodeId);
            const root = document.createElement("div");
            root.className = "amap-route-popup";
            let actionsHtml = "";
            actionsHtml += `<button type="button" data-node-action="start">设为起点</button>`;
            actionsHtml += `<button type="button" data-node-action="end">设为终点</button>`;
            actionsHtml += `<button type="button" data-node-action="target">加入途经点</button>`;
            if (isEnd) {
                actionsHtml += `<button type="button" data-node-action="remove-end">移除终点</button>`;
            }
            if (isTarget) {
                actionsHtml += `<button type="button" data-node-action="remove-target">从路径删除</button>`;
            }
            if (isIndoorBuildingNode(node)) {
                actionsHtml += `<button type="button" data-node-action="indoor">进入室内导航</button>`;
            }
            root.innerHTML = (
                `<button class="amap-popup-close" type="button" aria-label="关闭">x</button>` +
                `<strong>${htmlEscape(node.name)}</strong>` +
                `<small>${htmlEscape(node.category)}</small>` +
                `<div class="route-popup-actions">${actionsHtml}</div>`
            );
            root.querySelector(".amap-popup-close").addEventListener("click", function () {
                infoWindow.close();
            });
            root.querySelectorAll("[data-node-action]").forEach(function (button) {
                button.addEventListener("click", function () {
                    const action = button.getAttribute("data-node-action");
                    if (action === "target") {
                        ensureWaypointRouteMode();
                        if (!setTargetValue(node.id, true)) {
                            return;
                        }
                    } else if (action === "remove-target") {
                        setTargetValue(node.id, false);
                    } else if (action === "remove-end") {
                        setSelectValue(endSelect, "");
                    } else if (action === "indoor") {
                        openIndoorNavigation(node);
                        return;
                    } else {
                        setRouteEndpoint(action === "start" ? "start" : "end", node.id);
                    }
                    infoWindow.close();
                    submitPlanner();
                });
            });
            return root;
        }

        function openNodePopup(node) {
            const position = nodeLngLat(node);
            if (!position) {
                return;
            }
            infoWindow.setContent(popupContent(node));
            infoWindow.open(map, position);
        }

        if (!collectMode && false) {
        selectableNodes.forEach(function (node) {
            const position = nodeLngLat(node);
            const nodeId = String(node.id);
            const isStartNode = nodeId === currentStartId();
            const isEndNode = nodeId === currentEndId();
            const targetItems = normalizedTargetItems();
            const targetIndex = targetItems.findIndex(function (item) { return item.id === nodeId; });
            const isSelectedTarget = targetIndex !== -1;
            const markerStateClass = isStartNode || isEndNode || isSelectedTarget ? "is-selected" : "";
            const marker = new AMap.Marker({
                position,
                title: node.name,
                content: routePointMarkerContent(node, `route-planning-marker ${markerStateClass}`),
                anchor: "center",
                offset: new AMap.Pixel(0, 0),
                zIndex: markerStateClass ? 80 : 60
            });
            poiMarkers.push(marker);

            let badgeText = "";
            let badgeClass = "";
            if (isStartNode) {
                badgeText = "始";
                badgeClass = "is-start";
            } else if (isEndNode) {
                badgeText = "\u672b";
                badgeClass = "is-end";
            } else if (isSelectedTarget) {
                badgeText = String(targetIndex + 1);
                badgeClass = "is-waypoint";
            }
            if (badgeText) {
                const badgeMarker = new AMap.Marker({
                    position,
                    content: `<div class="route-target-number route-planning-badge ${badgeClass}"><span>${badgeText}</span></div>`,
                    anchor: "center",
                    zIndex: 95
                });
                poiMarkers.push(badgeMarker);
            }
        });
        if (poiMarkers.length) {
            map.add(poiMarkers);
        }
        }

        function mapBoundsContains(point) {
            if (!point || point.length < 2) {
                return false;
            }
            const bounds = map.getBounds && map.getBounds();
            if (!bounds) {
                return true;
            }
            if (typeof bounds.contains === "function") {
                return bounds.contains(point);
            }
            return true;
        }

        function isRoadNode(node) {
            return String((node || {}).kind || "").trim() === "road";
        }

        function planningTargetInfo(nodeId) {
            const id = String(nodeId || "");
            const targetItems = normalizedTargetItems();
            const waypointIndex = targetItems.findIndex(function (item) { return item.id === id; });
            if (id && id === currentStartId()) {
                return { selected: true, badge: "始", badgeClass: "is-start" };
            }
            if (id && id === currentEndId()) {
                return { selected: true, badge: "末", badgeClass: "is-end" };
            }
            if (waypointIndex !== -1) {
                return { selected: true, badge: String(waypointIndex + 1), badgeClass: "is-waypoint" };
            }
            return { selected: false, badge: "", badgeClass: "" };
        }

        function shouldShowPlanningNode(node, info) {
            const position = nodeLngLat(node);
            if (!position) {
                return false;
            }
            if (info && info.selected) {
                return true;
            }
            const zoom = map.getZoom();
            if (zoom < 17) {
                return false;
            }
            return mapBoundsContains(position);
        }

        function routeClickRadiusForZoom() {
            const zoom = map.getZoom();
            if (zoom < 17) {
                return 18;
            }
            if (zoom < 18) {
                return 28;
            }
            return routeClickRadiusMeters;
        }

        function planningMarkerExtraClass(info) {
            const zoom = map.getZoom();
            const classes = ["route-planning-marker", mapZoomTierClass()];
            if (info.selected) {
                classes.push("is-selected");
            } else {
                classes.push("is-muted");
            }
            if (!info.selected && zoom < 18) {
                classes.push("is-label-hidden");
            }
            return classes.join(" ");
        }

        function mapZoomTierClass() {
            const zoom = map.getZoom();
            if (zoom >= 18.8) {
                return "is-zoom-close";
            }
            if (zoom >= 17.8) {
                return "is-zoom-mid";
            }
            return "is-zoom-far";
        }

        function redrawPlanningMarkers() {
            if (collectMode) {
                return;
            }
            removeOverlayList(poiMarkers);
            selectableNodes.forEach(function (node) {
                const position = nodeLngLat(node);
                const nodeId = String(node.id);
                const info = planningTargetInfo(nodeId);
                if (!shouldShowPlanningNode(node, info)) {
                    return;
                }
                poiMarkers.push(new AMap.Marker({
                    position,
                    title: node.name,
                    content: routePointMarkerContent(node, planningMarkerExtraClass(info)),
                    anchor: "center",
                    offset: new AMap.Pixel(0, 0),
                    zIndex: info.selected ? 118 : 108
                }));
                if (info.badge) {
                    poiMarkers.push(new AMap.Marker({
                        position,
                        content: `<div class="route-target-number route-planning-badge ${info.badgeClass}"><span>${info.badge}</span></div>`,
                        anchor: "center",
                        zIndex: 121
                    }));
                }
            });
            if (poiMarkers.length) {
                map.add(poiMarkers);
            }
        }

        redrawPlanningMarkers();
        let planningMarkerTimer = null;
        function schedulePlanningMarkerRedraw() {
            window.clearTimeout(planningMarkerTimer);
            planningMarkerTimer = window.setTimeout(redrawPlanningMarkers, 80);
        }
        map.on("zoomend", schedulePlanningMarkerRedraw);
        map.on("moveend", schedulePlanningMarkerRedraw);

        const facilityMarkers = [];
        let facilityLayerVisible = false;
        function shouldShowFacilityMarker(facility, position) {
            if (!position) {
                return false;
            }
            if (map.getZoom() < 18.4) {
                return false;
            }
            return mapBoundsContains(position);
        }

        function redrawFacilityMarkers() {
            if (collectMode || !facilityLayerVisible) {
                removeOverlayList(facilityMarkers);
                return;
            }
            removeOverlayList(facilityMarkers);
            facilities.forEach(function (facility) {
                const position = facilityLngLat(facility);
                if (!shouldShowFacilityMarker(facility, position)) {
                    return;
                }
                const displayName = facilityDisplayName(facility);
                const nearestPosition = facilityConnectionPosition(facility, position);
                if (nearestPosition) {
                    facilityMarkers.push(new AMap.Polyline({
                        path: [position, nearestPosition],
                        strokeColor: "#78c8ba",
                        strokeWeight: 3,
                        strokeOpacity: 0.72,
                        strokeStyle: "dashed",
                        lineJoin: "round",
                        lineCap: "round",
                        zIndex: 49
                    }));
                }
                facilityMarkers.push(new AMap.Marker({
                    position,
                    title: displayName,
                    content: facilityMarkerContent(facility, `route-facility-marker ${mapZoomTierClass()}`),
                    anchor: "center",
                    zIndex: 84
                }));
            });
            if (facilityMarkers.length) {
                map.add(facilityMarkers);
            }
        }

        redrawFacilityMarkers();
        let facilityMarkerTimer = null;
        function scheduleFacilityMarkerRedraw() {
            if (!facilityLayerVisible || collectMode) {
                return;
            }
            window.clearTimeout(facilityMarkerTimer);
            facilityMarkerTimer = window.setTimeout(redrawFacilityMarkers, 120);
        }
        map.on("zoomend", scheduleFacilityMarkerRedraw);
        map.on("moveend", scheduleFacilityMarkerRedraw);
        if (showFacilityLayerToggle) {
            showFacilityLayerToggle.addEventListener("click", function () {
                facilityLayerVisible = !facilityLayerVisible;
                syncLayerToggleButton(showFacilityLayerToggle, facilityLayerVisible);
                redrawFacilityMarkers();
            });
        }

        function nearestSelectable(lng, lat) {
            let closest = null;
            selectableNodes.forEach(function (node) {
                const position = nodeLngLat(node);
                if (!position) {
                    return;
                }
                const distance = haversine(lat, lng, position[1], position[0]);
                if (!closest || distance < closest.distance) {
                    closest = { node, distance };
                }
            });
            return closest;
        }

        function nearestGraphNodePosition(position, options) {
            const roadOnly = !options || options.roadOnly !== false;
            let closest = null;
            nodes.forEach(function (node) {
                if (roadOnly && !isRoadNode(node)) {
                    return;
                }
                const nodePosition = nodeLngLat(node);
                if (!nodePosition) {
                    return;
                }
                const distance = haversine(position[1], position[0], nodePosition[1], nodePosition[0]);
                if (!closest || distance < closest.distance) {
                    closest = { position: nodePosition, distance };
                }
            });
            return closest ? closest.position : null;
        }

        function facilityConnectionPosition(facility, position) {
            const anchor = [Number(facility.nearest_lng), Number(facility.nearest_lat)];
            if (Number.isFinite(anchor[0]) && Number.isFinite(anchor[1])) {
                return anchor;
            }
            const nearestId = String(facility.nearest_node || "");
            const nearestNode = nearestId ? nodeById.get(nearestId) : null;
            if (nearestNode && isRoadNode(nearestNode)) {
                return nodeLngLat(nearestNode);
            }
            return nearestGraphNodePosition(position, { roadOnly: true });
        }

        function setupCollector() {
            if (!data.amap || !data.amap.collectMode) {
                return false;
            }
            const panel = document.createElement("section");
            panel.className = "road-editor-panel collector-panel";
            panel.innerHTML = (
                "<strong>手动采集模式</strong>" +
                "<p>路线点用于模块二规划；场所用于模块三查询，只绑定最近路网节点并按图距离排序。</p>" +
                "<div class=\"collector-tabs\">" +
                "<button type=\"button\" class=\"is-active\" data-collector-mode=\"poi\">路线点</button>" +
                "<button type=\"button\" data-collector-mode=\"road\">道路</button>" +
                "<button type=\"button\" data-collector-mode=\"snap\">吸附</button>" +
                "<button type=\"button\" data-collector-mode=\"facility\">场所</button>" +
                "</div>" +
                "<button type=\"button\" class=\"collector-map-lock\" data-editor-action=\"toggle-map-lock\">锁定地图编辑</button>" +
                "<div class=\"collector-mode-note\" id=\"collectorModeNote\"></div>" +
                "<label data-fields=\"poi facility road\">名称<input id=\"collectorName\" type=\"text\" value=\"采集点\"></label>" +
                "<label data-fields=\"poi\">路线点类型<select id=\"collectorKind\"><option value=\"building\">建筑</option><option value=\"gate\">校门</option><option value=\"teaching\">教学楼</option><option value=\"library\">图书馆</option><option value=\"canteen\">食堂</option><option value=\"dorm\">宿舍</option><option value=\"sports\">体育</option><option value=\"service\">服务点</option><option value=\"landmark\">地标</option></select></label>" +
                "<label data-fields=\"facility\">场所类别<select id=\"collectorFacilityType\"><option value=\"卫生间\">卫生间</option><option value=\"超市\">超市</option><option value=\"便利店\">便利店</option><option value=\"餐饮\">餐饮</option><option value=\"医疗\">医疗</option><option value=\"快递\">快递</option><option value=\"ATM\">ATM</option><option value=\"公交\">公交</option><option value=\"停车\">停车</option><option value=\"饮水\">饮水</option><option value=\"休息点\">休息点</option><option value=\"其他\">其他</option></select></label>" +
                "<label data-fields=\"facility\">菜系细分<select id=\"collectorCuisine\"><option value=\"\">按店名自动识别</option><option value=\"东北菜\">东北菜</option><option value=\"川菜\">川菜</option><option value=\"湘菜\">湘菜</option><option value=\"火锅\">火锅</option><option value=\"自助\">自助</option><option value=\"烧烤\">烧烤</option><option value=\"快餐\">快餐</option><option value=\"奶茶\">奶茶</option><option value=\"咖啡\">咖啡</option><option value=\"小吃\">小吃</option><option value=\"面食\">面食</option><option value=\"粉面\">粉面</option><option value=\"粤菜\">粤菜</option><option value=\"西餐\">西餐</option><option value=\"印度菜\">印度菜</option><option value=\"家常菜\">家常菜</option><option value=\"食堂\">食堂</option><option value=\"超市便利\">超市便利</option><option value=\"饮品\">饮品</option><option value=\"其他餐饮\">其他餐饮</option></select></label>" +
                "<label data-fields=\"facility\" id=\"collectorCustomCuisineWrap\" hidden>手动菜系<input id=\"collectorCustomCuisine\" type=\"text\" value=\"\" placeholder=\"例如：闽南菜、韩餐、轻食\"></label>" +
                "<label data-fields=\"facility\">自定义标签<input id=\"collectorCategory\" type=\"text\" value=\"\" placeholder=\"选其他时填写；也可补充多个标签\"></label>" +
                "<div class=\"collector-road-section collector-road-section--type\" data-fields=\"road\">" +
                "<div class=\"collector-section-title\">道路属性</div>" +
                "<label class=\"collector-road-field\" data-fields=\"road\"><span>道路类型</span><select id=\"collectorRoadType\"><option value=\"main\">主干道</option><option value=\"walkway\" selected>普通步道</option><option value=\"narrow\">狭窄小路</option><option value=\"stairs\">楼间通道/台阶</option></select></label>" +
                "</div>" +
                "<div class=\"collector-road-section collector-road-section--settings\" data-fields=\"road\">" +
                "<div class=\"collector-section-title\">通行设置</div>" +
                "<div class=\"collector-road-options\" data-fields=\"road\">" +
                "<label class=\"collector-toggle-chip\"><input id=\"collectorWalk\" type=\"checkbox\" checked><span>步行可达</span></label>" +
                "<label class=\"collector-toggle-chip\"><input id=\"collectorBike\" type=\"checkbox\" checked><span>自行车可达</span></label>" +
                "<label class=\"collector-number-field\"><span>拥挤度</span><input id=\"collectorCongestion\" type=\"number\" min=\"0.1\" max=\"1\" step=\"0.05\" value=\"0.82\"></label>" +
                "<button type=\"button\" class=\"collector-preset-button\" data-editor-action=\"apply-road-preset\">应用道路预设</button>" +
                "</div>" +
                "<div class=\"collector-road-hint\">主干道更适合双向通行，步道和台阶会自动降低自行车可达性。</div>" +
                "</div>" +
                "<div class=\"road-editor-actions road-editor-actions--utility\">" +
                "<button type=\"button\" data-editor-action=\"undo-step\">撤销上步</button>" +
                "<button type=\"button\" data-editor-action=\"redo-step\">重做</button>" +
                "<button type=\"button\" data-editor-action=\"clear\">清空当前线</button>" +
                "</div>" +
                "<div class=\"road-editor-actions road-editor-actions--commit\">" +
                "<button type=\"button\" data-editor-action=\"save-road\">保存道路</button>" +
                "<button type=\"button\" data-editor-action=\"clear-all\">清空全部</button>" +
                "</div>" +
                "<textarea id=\"roadEditorOutput\" readonly placeholder=\"采集状态会显示在这里\"></textarea>"
            );
            mapEl.parentElement.appendChild(panel);

            const output = panel.querySelector("#roadEditorOutput");
            const modeNote = panel.querySelector("#collectorModeNote");
            const nameInput = panel.querySelector("#collectorName");
            const kindInput = panel.querySelector("#collectorKind");
            const facilityTypeInput = panel.querySelector("#collectorFacilityType");
            const cuisineInput = panel.querySelector("#collectorCuisine");
            const customCuisineWrap = panel.querySelector("#collectorCustomCuisineWrap");
            const customCuisineInput = panel.querySelector("#collectorCustomCuisine");
            const categoryInput = panel.querySelector("#collectorCategory");
            const roadTypeInput = panel.querySelector("#collectorRoadType");
            const walkInput = panel.querySelector("#collectorWalk");
            const bikeInput = panel.querySelector("#collectorBike");
            const congestionInput = panel.querySelector("#collectorCongestion");
            const mapLockButton = panel.querySelector(".collector-map-lock");
            const editMarkers = [];
            const savedOverlays = [];
            const savedTransientOverlays = [];
            const snapHighlightOverlays = [];
            const editLines = [];
            const editLinkLines = [];
            let editPoints = [];
            let editBreaks = [];
            let pointPoiLinks = [];
            let pointRoadLinks = [];
            let selectedEditIndex = -1;
            let selectedSavedRoadPoint = null;
            let selectedPoiTarget = null;
            let undoStack = [];
            let redoStack = [];
            let rightDrawing = false;
            let savingRoad = false;
            let lastRightActionAt = 0;
            let draggingEditIndex = -1;
            let lastDragPoint = null;
            let lastDragBearing = null;
            let suppressNextClick = false;
            let mapLocked = true;
            let collectorMode = "poi";
            let selectedSnapEndpoints = [];
            let collectorState = { nodes: [], edges: [], links: [], facilities: [] };
            let collectorNodeMap = new Map();
            let collectorFacilityMap = new Map();
            let collectorEdgeMap = new Map();
            let collectorRoadPointCache = [];
            let collectorRoadPointCacheDirty = true;
            let collectorRoadPointCount = 0;
            let collectorRoadPointGrid = new Map();
            let collectorEdgeGrid = new Map();
            let collectorNamedGrid = new Map();
            let collectorEdgeBounds = new Map();
            let collectorRenderViewportBox = null;
            const collectorGridLngStep = 0.00036;
            const collectorGridLatStep = 0.00028;
            const maxSnapDistanceMeters = 90;
            const maxVisibleSnapRoadMarkers = 180;
            const boxSelect = {
                pressed: false,
                active: false,
                startX: 0,
                startY: 0,
                currentX: 0,
                currentY: 0,
                startedAt: 0,
                cancelled: false
            };
            const boxSelectOverlay = document.createElement("div");
            boxSelectOverlay.className = "collector-box-select";
            boxSelectOverlay.hidden = true;
            mapEl.appendChild(boxSelectOverlay);

            async function requestCollector(path, options) {
                const response = await fetch(path, {
                    headers: { "Content-Type": "application/json" },
                    credentials: "same-origin",
                    ...(options || {})
                });
                const payload = await response.json();
                if (!response.ok || payload.error) {
                    throw new Error(payload.error || "采集请求失败");
                }
                return payload;
            }

            function status(message) {
                output.value = message;
            }

            function flashConfirmButton(action) {
                const button = panel.querySelector(`[data-editor-action="${action}"]`);
                if (!button) {
                    return;
                }
                button.classList.add("is-confirmed");
                window.setTimeout(function () {
                    button.classList.remove("is-confirmed");
                }, 650);
            }

            const roadPresets = {
                main: { congestion: 0.95, walk: true, bike: true },
                walkway: { congestion: 0.82, walk: true, bike: true },
                narrow: { congestion: 0.68, walk: true, bike: false },
                stairs: { congestion: 0.55, walk: true, bike: false }
            };

            function roadConfig() {
                const congestion = Math.min(1, Math.max(0.1, Number(congestionInput.value || 0.82)));
                return {
                    road_type: roadTypeInput.value || "walkway",
                    walk: Boolean(walkInput.checked),
                    bike: Boolean(bikeInput.checked),
                    congestion
                };
            }

            function selectedOptionText(selectEl) {
                const option = selectEl && selectEl.options ? selectEl.options[selectEl.selectedIndex] : null;
                return option ? option.textContent.trim() : "";
            }

            function facilityTypeValue() {
                const preset = facilityTypeInput.value || "服务设施";
                const custom = (categoryInput.value || "").trim();
                return preset === "其他" && custom ? custom : preset;
            }

            function cuisineValue() {
                const selected = cuisineInput ? String(cuisineInput.value || "").trim() : "";
                if (selected === "其他餐饮") {
                    const custom = customCuisineInput ? String(customCuisineInput.value || "").trim() : "";
                    if (!custom) {
                        throw new Error("选择其他餐饮时，请手动填写菜系。");
                    }
                    return custom;
                }
                return selected;
            }

            function syncCuisineCustomInput() {
                const showCustom = cuisineInput && cuisineInput.value === "其他餐饮";
                if (customCuisineWrap) {
                    customCuisineWrap.hidden = !showCustom || collectorMode !== "facility";
                }
                if (!showCustom && customCuisineInput) {
                    customCuisineInput.value = "";
                }
            }

            function applyRoadPreset() {
                const preset = roadPresets[roadTypeInput.value] || roadPresets.walkway;
                congestionInput.value = preset.congestion.toFixed(2);
                walkInput.checked = preset.walk;
                bikeInput.checked = preset.bike;
                status(`已应用道路预设：拥挤度 ${congestionInput.value}，${walkInput.checked ? "步行可达" : "步行禁行"}，${bikeInput.checked ? "自行车可达" : "自行车禁行"}。`);
            }

            function modeStatusMessage() {
                if (collectorMode === "poi") {
                    return "路线点模式：点击地图保存可规划地点，随后用吸附模式把它接入道路。";
                }
                if (collectorMode === "facility") {
                    return "场所模式：点击地图保存卫生间、超市等服务设施；它只参与模块三查询，不出现在路线规划中。";
                }
                if (collectorMode === "snap") {
                    return "吸附模式：点击两个相近端点会立即连接；支持路点-路点、路点-路线点、路点-场所。误连可用撤销上步。";
                }
                return "道路模式：先选道路类型和拥挤度，再右键连续描路；保存后整条道路统一使用这些参数。";
            }

            function updateCollectorModeFields() {
                panel.querySelectorAll("[data-fields]").forEach(function (element) {
                    const modes = (element.getAttribute("data-fields") || "").split(/\s+/);
                    element.hidden = modes.indexOf(collectorMode) === -1;
                });
                if (modeNote) {
                    modeNote.textContent = modeStatusMessage();
                }
                syncCuisineCustomInput();
            }

            function consumeMapEvent(event) {
                if (!event) {
                    return;
                }
                if (event.preventDefault) {
                    event.preventDefault();
                }
                if (event.stopPropagation) {
                    event.stopPropagation();
                }
                if (event.originEvent) {
                    consumeMapEvent(event.originEvent);
                }
            }

            function captureMapView() {
                if (!map || !map.getCenter || !map.getZoom) {
                    return null;
                }
                const center = map.getCenter();
                if (!center) {
                    return null;
                }
                return {
                    center: [center.getLng(), center.getLat()],
                    zoom: map.getZoom()
                };
            }

            function restoreMapView(view) {
                if (!view || !view.center) {
                    return;
                }
                window.setTimeout(function () {
                    map.setZoomAndCenter(view.zoom, view.center);
                }, 0);
            }

            function finishDrawingFromOverlay(event, message) {
                if (!rightDrawing) {
                    return false;
                }
                consumeMapEvent(event);
                suppressNextClick = true;
                finishRightDrawingAndSave(message || "连续打点已结束，正在保存道路。");
                return true;
            }

            function applyMapMotionState() {
                const shouldLock = mapLocked || rightDrawing;
                map.setStatus({
                    dragEnable: !shouldLock,
                    doubleClickZoom: false,
                    keyboardEnable: !shouldLock
                });
                if (collectorMode === "snap") {
                    mapLockButton.textContent = shouldLock
                        ? "吸附模式：地图已锁定"
                        : "吸附模式：地图可拖动";
                } else {
                    mapLockButton.textContent = shouldLock
                        ? "地图已锁定：可框选删除"
                        : "地图可拖动：移动视野";
                }
                mapLockButton.classList.toggle("is-unlocked", !shouldLock);
                mapLockButton.disabled = false;
            }

            function editorSnapshot() {
                return {
                    points: editPoints.map(function (point) { return [point[0], point[1]]; }),
                    breaks: editBreaks.slice(),
                    links: pointPoiLinks.map(function (link) { return { index: link.index, poi: link.poi }; }),
                    roadLinks: pointRoadLinks.map(function (link) { return { index: link.index, edge: link.edge, target_index: link.target_index }; }),
                    selected: selectedEditIndex,
                    selectedRoad: selectedSavedRoadPoint ? { ...selectedSavedRoadPoint } : null,
                    selectedPoi: selectedPoiTarget ? { ...selectedPoiTarget } : null,
                    selectedSnapEndpoints: selectedSnapEndpoints.map(function (endpoint) { return { ...endpoint }; })
                };
            }

            function clonePayload(value) {
                return JSON.parse(JSON.stringify(value || null));
            }

            function collectorCellKey(lng, lat) {
                const cellX = Math.floor(Number(lng) / collectorGridLngStep);
                const cellY = Math.floor(Number(lat) / collectorGridLatStep);
                return `${cellX}:${cellY}`;
            }

            function collectorCellRangeForBox(box, paddingLng, paddingLat) {
                if (!box) {
                    return null;
                }
                const west = Number(box.west) - Number(paddingLng || 0);
                const east = Number(box.east) + Number(paddingLng || 0);
                const south = Number(box.south) - Number(paddingLat || 0);
                const north = Number(box.north) + Number(paddingLat || 0);
                return {
                    minX: Math.floor(west / collectorGridLngStep),
                    maxX: Math.floor(east / collectorGridLngStep),
                    minY: Math.floor(south / collectorGridLatStep),
                    maxY: Math.floor(north / collectorGridLatStep)
                };
            }

            function collectorBoxFromBounds(bounds, paddingRatio) {
                if (!bounds) {
                    return null;
                }
                const southWest = bounds.getSouthWest && bounds.getSouthWest();
                const northEast = bounds.getNorthEast && bounds.getNorthEast();
                if (!southWest || !northEast) {
                    return null;
                }
                const west = typeof southWest.getLng === "function" ? southWest.getLng() : southWest.lng;
                const south = typeof southWest.getLat === "function" ? southWest.getLat() : southWest.lat;
                const east = typeof northEast.getLng === "function" ? northEast.getLng() : northEast.lng;
                const north = typeof northEast.getLat === "function" ? northEast.getLat() : northEast.lat;
                const lngPad = Math.max((east - west) * (paddingRatio || 0), 0.00018);
                const latPad = Math.max((north - south) * (paddingRatio || 0), 0.00014);
                return {
                    west: west - lngPad,
                    south: south - latPad,
                    east: east + lngPad,
                    north: north + latPad
                };
            }

            function collectorPointBox(point, radiusMeters) {
                if (!point || point.length < 2) {
                    return null;
                }
                const latRadius = Number(radiusMeters || 0) / 111320;
                const lngRadius = Number(radiusMeters || 0) / (111320 * Math.max(Math.cos(Number(point[1]) * Math.PI / 180), 0.2));
                return {
                    west: Number(point[0]) - lngRadius,
                    east: Number(point[0]) + lngRadius,
                    south: Number(point[1]) - latRadius,
                    north: Number(point[1]) + latRadius
                };
            }

            function collectorGridItems(grid, box, valueKey) {
                const range = collectorCellRangeForBox(box, 0, 0);
                if (!range) {
                    return [];
                }
                const seen = new Set();
                const items = [];
                for (let x = range.minX; x <= range.maxX; x += 1) {
                    for (let y = range.minY; y <= range.maxY; y += 1) {
                        const bucket = grid.get(`${x}:${y}`);
                        if (!bucket || !bucket.length) {
                            continue;
                        }
                        bucket.forEach(function (entry) {
                            const key = valueKey ? entry[valueKey] : entry;
                            if (seen.has(key)) {
                                return;
                            }
                            seen.add(key);
                            items.push(entry);
                        });
                    }
                }
                return items;
            }

            function collectorBoxContainsPoint(box, point) {
                return !!(box && point && point.length >= 2
                    && Number(point[0]) >= box.west
                    && Number(point[0]) <= box.east
                    && Number(point[1]) >= box.south
                    && Number(point[1]) <= box.north);
            }

            function rebuildCollectorLookupCaches() {
                collectorNodeMap = new Map((collectorState.nodes || []).map(function (item) {
                    return [String(item.id), item];
                }));
                collectorFacilityMap = new Map((collectorState.facilities || []).map(function (item) {
                    return [String(item.id), item];
                }));
                collectorEdgeMap = new Map((collectorState.edges || []).map(function (item) {
                    return [String(item.id), item];
                }));
            }

            function collectorSnapshot() {
                return {
                    nodes: clonePayload(collectorState.nodes || []),
                    edges: clonePayload(collectorState.edges || []),
                    links: clonePayload(collectorState.links || []),
                    facilities: clonePayload(collectorState.facilities || []),
                    meta: clonePayload(collectorState.meta || {}),
                    editor: editorSnapshot()
                };
            }

            function pushUndoSnapshot() {
                undoStack.push(collectorSnapshot());
                if (undoStack.length > 80) {
                    undoStack.shift();
                }
                redoStack = [];
            }

            const pushEditorHistory = pushUndoSnapshot;

            async function restoreCollectorSnapshot(snapshot) {
                if (!snapshot) {
                    return;
                }
                if (snapshot.editor) {
                    restoreEditorSnapshot(snapshot.editor);
                }
                const payload = await requestCollector("/api/collector/restore", {
                    method: "POST",
                    body: JSON.stringify({
                        nodes: snapshot.nodes || [],
                        edges: snapshot.edges || [],
                        links: snapshot.links || [],
                        facilities: snapshot.facilities || [],
                        meta: snapshot.meta || {}
                    })
                });
                collectorState = {
                    nodes: snapshot.nodes || [],
                    edges: snapshot.edges || [],
                    links: snapshot.links || [],
                    facilities: snapshot.facilities || [],
                    meta: snapshot.meta || {},
                    graph: payload.graph,
                    summary: payload.summary
                };
                rebuildCollectorLookupCaches();
                collectorRoadPointCacheDirty = true;
                updateConnectorOptions();
                redrawSaved();
            }

            function pushEditorHistoryIfChanged() {
                const snapshot = editorSnapshot();
                const latest = undoStack[undoStack.length - 1];
                if (!latest || JSON.stringify(latest.editor) !== JSON.stringify(snapshot)) {
                    pushUndoSnapshot();
                }
            }

            function restoreEditorSnapshot(snapshot) {
                editPoints = snapshot.points.map(function (point) { return [point[0], point[1]]; });
                editBreaks = (snapshot.breaks || []).slice();
                pointPoiLinks = (snapshot.links || []).map(function (link) { return { index: link.index, poi: link.poi }; });
                pointRoadLinks = (snapshot.roadLinks || []).map(function (link) { return { index: link.index, edge: link.edge, target_index: link.target_index }; });
                selectedEditIndex = snapshot.selected;
                selectedSavedRoadPoint = snapshot.selectedRoad || null;
                selectedPoiTarget = snapshot.selectedPoi || null;
                selectedSnapEndpoints = snapshot.selectedSnapEndpoints || [];
                redrawEditor();
                redrawSaved();
            }

            function addEditPoint(point, useHistory) {
                if (useHistory !== false) {
                    pushEditorHistory();
                }
                editPoints.push(point);
                selectedEditIndex = editPoints.length - 1;
                redrawEditor();
            }

            function segmentRanges() {
                const ranges = [];
                let start = 0;
                const sortedBreaks = editBreaks
                    .filter(function (index) { return index >= 0 && index < editPoints.length - 1; })
                    .sort(function (a, b) { return a - b; });
                sortedBreaks.forEach(function (breakIndex) {
                    if (breakIndex >= start) {
                        ranges.push([start, breakIndex + 1]);
                        start = breakIndex + 1;
                    }
                });
                ranges.push([start, editPoints.length]);
                return ranges.filter(function (range) { return range[1] - range[0] >= 2; });
            }

            function poiNameById(poiId) {
                const node = collectorNodeMap.get(String(poiId)) || null;
                return node ? node.name : poiId;
            }

            function poiPointById(poiId) {
                const node = collectorNodeMap.get(String(poiId)) || null;
                return node ? [Number(node.amap_lng), Number(node.amap_lat)] : null;
            }

            function facilityById(facilityId) {
                return collectorFacilityMap.get(String(facilityId)) || null;
            }

            function facilityPointById(facilityId) {
                const facility = facilityById(facilityId);
                return facility ? [Number(facility.amap_lng), Number(facility.amap_lat)] : null;
            }

            function graphNodePointById(nodeId) {
                const localNode = collectorNodeMap.get(String(nodeId));
                if (localNode) {
                    return [Number(localNode.amap_lng), Number(localNode.amap_lat)];
                }
                const graphNodes = collectorState.graph && collectorState.graph.nodes ? collectorState.graph.nodes : [];
                const node = graphNodes.find(function (item) { return item.id === nodeId; });
                if (node) {
                    return [Number(node.amap_lng), Number(node.amap_lat)];
                }
                const roadMatch = /^road_(.+)_(\d{3})$/.exec(String(nodeId));
                if (roadMatch) {
                    const edge = collectorEdgeMap.get(roadMatch[1]);
                    if (edge && edge.amap_geometry && edge.amap_geometry[Number(roadMatch[2])]) {
                        const point = edge.amap_geometry[Number(roadMatch[2])];
                        return [Number(point[0]), Number(point[1])];
                    }
                }
                return null;
            }

            function nearestCollectorGraphPoint(position) {
                const graphNodes = (collectorState.graph && collectorState.graph.nodes ? collectorState.graph.nodes : []).concat(collectorState.nodes || []);
                let closest = null;
                graphNodes.forEach(function (node) {
                    if (node.amap_lng == null || node.amap_lat == null) {
                        return;
                    }
                    const nodePosition = [Number(node.amap_lng), Number(node.amap_lat)];
                    const distance = haversine(position[1], position[0], nodePosition[1], nodePosition[0]);
                    if (!closest || distance < closest.distance) {
                        closest = { position: nodePosition, distance };
                    }
                });
                return closest ? closest.position : null;
            }

            function roadGraphNodeId(endpoint) {
                if (!endpoint || endpoint.type !== "road") {
                    return "";
                }
                return `road_${endpoint.edge}_${String(endpoint.point_index).padStart(3, "0")}`;
            }

            function roadPointByLink(link) {
                const edge = collectorEdgeMap.get(String(link.edge)) || null;
                if (!edge || !edge.amap_geometry || !edge.amap_geometry[link.target_index]) {
                    return null;
                }
                const point = edge.amap_geometry[link.target_index];
                return [Number(point[0]), Number(point[1])];
            }

            function roadPointByRef(ref) {
                const edge = collectorEdgeMap.get(String(ref.edge)) || null;
                if (!edge || !edge.amap_geometry || !edge.amap_geometry[ref.point_index]) {
                    return null;
                }
                const point = edge.amap_geometry[ref.point_index];
                return [Number(point[0]), Number(point[1])];
            }

            function rebuildCollectorRoadPointCache() {
                if (!collectorRoadPointCacheDirty) {
                    return collectorRoadPointCache;
                }
                collectorRoadPointCache = [];
                collectorRoadPointCount = 0;
                collectorRoadPointGrid = new Map();
                collectorEdgeGrid = new Map();
                collectorNamedGrid = new Map();
                collectorEdgeBounds = new Map();
                (collectorState.edges || []).forEach(function (edge) {
                    const geometry = edge.amap_geometry || [];
                    if (!geometry.length) {
                        return;
                    }
                    let west = Infinity;
                    let south = Infinity;
                    let east = -Infinity;
                    let north = -Infinity;
                    geometry.forEach(function (point, pointIndex) {
                        const lng = Number(point[0]);
                        const lat = Number(point[1]);
                        if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
                            return;
                        }
                        west = Math.min(west, lng);
                        south = Math.min(south, lat);
                        east = Math.max(east, lng);
                        north = Math.max(north, lat);
                        collectorRoadPointCount += 1;
                        const endpoint = {
                            type: "road",
                            edge: edge.id,
                            point_index: pointIndex,
                            name: edge.name || edge.id
                        };
                        const roadPoint = {
                            endpoint,
                            point: [lng, lat],
                            edge,
                            pointIndex
                        };
                        collectorRoadPointCache.push(roadPoint);
                        const cellKey = collectorCellKey(lng, lat);
                        if (!collectorRoadPointGrid.has(cellKey)) {
                            collectorRoadPointGrid.set(cellKey, []);
                        }
                        collectorRoadPointGrid.get(cellKey).push(roadPoint);
                    });
                    if (Number.isFinite(west) && Number.isFinite(south) && Number.isFinite(east) && Number.isFinite(north)) {
                        collectorEdgeBounds.set(String(edge.id), {
                            west,
                            south,
                            east,
                            north
                        });
                        const range = collectorCellRangeForBox({
                            west,
                            south,
                            east,
                            north
                        }, 0.00008, 0.00008);
                        if (range) {
                            for (let x = range.minX; x <= range.maxX; x += 1) {
                                for (let y = range.minY; y <= range.maxY; y += 1) {
                                    const key = `${x}:${y}`;
                                    if (!collectorEdgeGrid.has(key)) {
                                        collectorEdgeGrid.set(key, []);
                                    }
                                    collectorEdgeGrid.get(key).push(String(edge.id));
                                }
                            }
                        }
                    }
                });
                (collectorState.nodes || []).forEach(function (node) {
                    const point = [Number(node.amap_lng), Number(node.amap_lat)];
                    if (!Number.isFinite(point[0]) || !Number.isFinite(point[1])) {
                        return;
                    }
                    const cellKey = collectorCellKey(point[0], point[1]);
                    if (!collectorNamedGrid.has(cellKey)) {
                        collectorNamedGrid.set(cellKey, []);
                    }
                    collectorNamedGrid.get(cellKey).push({ kind: "node", item: node, point });
                });
                (collectorState.facilities || []).forEach(function (facility) {
                    const point = [Number(facility.amap_lng), Number(facility.amap_lat)];
                    if (!Number.isFinite(point[0]) || !Number.isFinite(point[1])) {
                        return;
                    }
                    const cellKey = collectorCellKey(point[0], point[1]);
                    if (!collectorNamedGrid.has(cellKey)) {
                        collectorNamedGrid.set(cellKey, []);
                    }
                    collectorNamedGrid.get(cellKey).push({ kind: "facility", item: facility, point });
                });
                collectorRoadPointCacheDirty = false;
                return collectorRoadPointCache;
            }

            function boundsContainsPoint(point) {
                if (!point || point.length < 2) {
                    return false;
                }
                const bounds = map.getBounds && map.getBounds();
                if (!bounds) {
                    return true;
                }
                if (typeof bounds.contains === "function") {
                    return bounds.contains(point);
                }
                const southWest = bounds.getSouthWest && bounds.getSouthWest();
                const northEast = bounds.getNorthEast && bounds.getNorthEast();
                if (!southWest || !northEast) {
                    return true;
                }
                const west = typeof southWest.getLng === "function" ? southWest.getLng() : southWest.lng;
                const south = typeof southWest.getLat === "function" ? southWest.getLat() : southWest.lat;
                const east = typeof northEast.getLng === "function" ? northEast.getLng() : northEast.lng;
                const north = typeof northEast.getLat === "function" ? northEast.getLat() : northEast.lat;
                return point[0] >= west && point[0] <= east && point[1] >= south && point[1] <= north;
            }

            function currentViewportBox(paddingRatio) {
                const bounds = map.getBounds && map.getBounds();
                return collectorBoxFromBounds(bounds, paddingRatio || 0);
            }

            function currentViewportRoadEdgeIds(paddingRatio) {
                const box = currentViewportBox(paddingRatio);
                if (!box) {
                    return [];
                }
                const candidates = collectorGridItems(collectorEdgeGrid, box, null);
                if (!candidates.length) {
                    return [];
                }
                return Array.from(new Set(candidates));
            }

            function currentViewportNamedCollectorItems(paddingRatio) {
                const box = currentViewportBox(paddingRatio);
                if (!box) {
                    return [];
                }
                return collectorGridItems(collectorNamedGrid, box, "item");
            }

            function collectorRoadMarkerRenderEnabled() {
                if (collectorMode === "snap") {
                    return true;
                }
                return Boolean(selectedSavedRoadPoint || selectedPoiTarget);
            }

            function shouldRenderSavedRoadPoint(point, isSelected) {
                if (isSelected) {
                    return true;
                }
                if (collectorMode === "snap") {
                    return isCollectorRoadFocusPoint(point);
                }
                return Boolean(selectedSavedRoadPoint || selectedPoiTarget) && isCollectorRoadFocusPoint(point);
            }

            function collectorRoadFocusPoints() {
                const points = [];
                const seen = new Set();

                function addPoint(point) {
                    if (!point) {
                        return;
                    }
                    const lng = Number(point[0]);
                    const lat = Number(point[1]);
                    if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
                        return;
                    }
                    const key = `${lng.toFixed(7)}:${lat.toFixed(7)}`;
                    if (seen.has(key)) {
                        return;
                    }
                    seen.add(key);
                    points.push([lng, lat]);
                }

                if (selectedSavedRoadPoint) {
                    addPoint(roadPointByRef(selectedSavedRoadPoint));
                }
                if (selectedPoiTarget) {
                    addPoint(poiPointById(selectedPoiTarget.id));
                }
                (selectedSnapEndpoints || []).forEach(function (endpoint) {
                    addPoint(endpointPoint(endpoint));
                });
                if (collectorMode === "road" && rightDrawing && editPoints.length) {
                    const step = Math.max(1, Math.floor(editPoints.length / 12));
                    editPoints.forEach(function (point, index) {
                        if (index === 0 || index === editPoints.length - 1 || index % step === 0) {
                            addPoint(point);
                        }
                    });
                }
                return points;
            }

            let collectorRoadFocusCache = [];
            let collectorRoadFocusRadiusCache = 0;

            function refreshCollectorRoadFocusCache() {
                collectorRoadFocusCache = collectorRoadFocusPoints();
                collectorRoadFocusRadiusCache = collectorRoadFocusRadiusMeters();
            }

            function collectorRoadFocusRadiusMeters() {
                const zoom = map && map.getZoom ? Number(map.getZoom()) : 18;
                if (zoom >= 19) {
                    return 34;
                }
                if (zoom >= 18.2) {
                    return 44;
                }
                if (zoom >= 17.4) {
                    return 58;
                }
                return 72;
            }

            function isCollectorRoadFocusPoint(point) {
                const focusPoints = collectorRoadFocusCache.length ? collectorRoadFocusCache : collectorRoadFocusPoints();
                if (!focusPoints.length || !point) {
                    return false;
                }
                const lng = Number(point[0]);
                const lat = Number(point[1]);
                if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
                    return false;
                }
                const radius = collectorRoadFocusRadiusCache || collectorRoadFocusRadiusMeters();
                return focusPoints.some(function (focusPoint) {
                    return haversine(lat, lng, Number(focusPoint[1]), Number(focusPoint[0])) <= radius;
                });
            }

            function pathTouchesViewport(path) {
                const box = collectorRenderViewportBox || currentViewportBox(0.01);
                return (path || []).some(function (point) {
                    return collectorBoxContainsPoint(box, point);
                });
            }

            function shouldRenderNamedCollectorMarker(point, isSelected) {
                if (isSelected) {
                    return true;
                }
                const box = collectorRenderViewportBox || currentViewportBox(0.04);
                return collectorBoxContainsPoint(box, point) && map.getZoom() >= 17.2;
            }

            function endpointPoint(endpoint) {
                if (!endpoint) {
                    return null;
                }
                if (endpoint.type === "poi") {
                    return poiPointById(endpoint.id);
                }
                if (endpoint.type === "facility") {
                    return facilityPointById(endpoint.id);
                }
                return roadPointByRef(endpoint);
            }

            function endpointKey(endpoint) {
                if (!endpoint) {
                    return "";
                }
                if (endpoint.type === "poi") {
                    return `poi:${endpoint.id}`;
                }
                if (endpoint.type === "facility") {
                    return `facility:${endpoint.id}`;
                }
                return `road:${endpoint.edge}:${endpoint.point_index}`;
            }

            function endpointLabel(endpoint) {
                if (!endpoint) {
                    return "";
                }
                if (endpoint.type === "poi") {
                    return `路线点：${endpoint.name || poiNameById(endpoint.id)}`;
                }
                if (endpoint.type === "facility") {
                    const facility = facilityById(endpoint.id);
                    return `场所：${endpoint.name || (facility && facility.name) || endpoint.id}`;
                }
                return `路点：${endpoint.name || endpoint.edge} #${Number(endpoint.point_index) + 1}`;
            }

            function snapEndpointSelected(endpoint) {
                const key = endpointKey(endpoint);
                return selectedSnapEndpoints.some(function (item) { return endpointKey(item) === key; });
            }

            async function selectSnapEndpoint(endpoint) {
                if (collectorMode !== "snap") {
                    return;
                }
                const key = endpointKey(endpoint);
                selectedSnapEndpoints = selectedSnapEndpoints.filter(function (item) {
                    return endpointKey(item) !== key;
                });
                selectedSnapEndpoints.push(endpoint);
                if (selectedSnapEndpoints.length > 2) {
                    selectedSnapEndpoints = selectedSnapEndpoints.slice(selectedSnapEndpoints.length - 2);
                }
                selectedPoiTarget = endpoint.type === "poi" ? { id: endpoint.id, name: endpoint.name } : null;
                selectedSavedRoadPoint = endpoint.type === "road"
                    ? { edge: endpoint.edge, target_index: endpoint.point_index, name: endpoint.name }
                    : null;
                redrawSnapSelectionHighlights();
                if (selectedSnapEndpoints.length === 2) {
                    await autoSnapSelectedEndpoints();
                } else {
                    redrawSavedV2Optimized();
                    status(`已选中 ${endpointLabel(endpoint)}，请继续点击另一个路节点、路线点或场所。`);
                }
            }

            function addSnapLine(collection, fromPoint, toPoint, selected) {
                if (!fromPoint || !toPoint) {
                    return;
                }
                collection.push(new AMap.Polyline({
                    path: [fromPoint, toPoint],
                    strokeColor: selected ? "#f2b15f" : "#85b8ad",
                    strokeWeight: selected ? 5 : 4,
                    strokeOpacity: selected ? 0.96 : 0.78,
                    strokeStyle: selected ? "solid" : "dashed",
                    lineJoin: "round",
                    lineCap: "round",
                    zIndex: selected ? 121 : 42
                }));
            }

            function addSnapEndpointHighlight(endpoint) {
                const point = endpointPoint(endpoint);
                if (!point) {
                    return;
                }
                let content = "";
                if (endpoint.type === "road") {
                    content = `<button type="button" class="saved-road-dot is-selected collector-snap-focus" aria-label="已选中路节点"></button>`;
                } else if (endpoint.type === "facility") {
                    const facility = facilityById(endpoint.id);
                    const name = endpoint.name || (facility && facility.name) || endpoint.id;
                    const typeLabel = facility ? facilityTypeLabel(facility) : "";
                    content = `<button type="button" class="facility-map-marker collector-facility-map-marker is-link-target collector-snap-focus" aria-label="已选中场所 ${htmlEscape(name)}"><span class="facility-map-dot"></span><span class="facility-map-label"><strong>${htmlEscape(name)}</strong><small>${htmlEscape(typeLabel)}</small></span></button>`;
                } else {
                    const name = endpoint.name || poiNameById(endpoint.id);
                    content = `<button type="button" class="route-point-map-marker collector-route-point-map-marker is-selected is-link-target collector-snap-focus" aria-label="已选中路线点 ${htmlEscape(name)}"><span class="route-point-map-dot"></span><span class="route-point-map-label">${htmlEscape(name)}</span></button>`;
                }
                snapHighlightOverlays.push(new AMap.Marker({
                    position: point,
                    content,
                    anchor: "center",
                    zIndex: 180
                }));
            }

            function redrawSnapSelectionHighlights() {
                removeOverlayList(snapHighlightOverlays);
                selectedSnapEndpoints.forEach(addSnapEndpointHighlight);
                if (selectedSnapEndpoints.length === 2) {
                    addSnapLine(
                        snapHighlightOverlays,
                        endpointPoint(selectedSnapEndpoints[0]),
                        endpointPoint(selectedSnapEndpoints[1]),
                        true
                    );
                }
                if (snapHighlightOverlays.length) {
                    map.add(snapHighlightOverlays);
                }
            }

            function clearCollectorOverlayLayers(useMapClear) {
                if (useMapClear && map && typeof map.clearMap === "function") {
                    map.clearMap();
                }
                removeOverlayList(editMarkers);
                removeOverlayList(savedOverlays);
                removeOverlayList(savedTransientOverlays);
                removeOverlayList(snapHighlightOverlays);
                removeOverlayList(editLines);
                removeOverlayList(editLinkLines);
                editMarkers.length = 0;
                savedOverlays.length = 0;
                savedTransientOverlays.length = 0;
                snapHighlightOverlays.length = 0;
                editLines.length = 0;
                editLinkLines.length = 0;
            }

            function nearestRoadEndpointOnEdgeFromScreen(edge, screenPoint) {
                if (!edge || !edge.amap_geometry || !screenPoint) {
                    return null;
                }
                const radius = collectorMode === "snap"
                    ? (map.getZoom() >= 18.4 ? 42 : 52)
                    : 28;
                let closest = null;
                edge.amap_geometry.forEach(function (point, pointIndex) {
                    const pixel = pointToContainer(point);
                    if (!pixel) {
                        return;
                    }
                    const distance = Math.hypot(pixel.x - screenPoint.x, pixel.y - screenPoint.y);
                    if (distance <= radius && (!closest || distance < closest.distance)) {
                        closest = {
                            endpoint: { type: "road", edge: edge.id, point_index: pointIndex, name: edge.name || edge.id },
                            point,
                            distance
                        };
                    }
                });
                return closest;
            }

            function createSavedRoadPolyline(edge, path) {
                const roadLine = new AMap.Polyline({
                    path,
                    strokeColor: "#8aaed8",
                    strokeWeight: collectorMode === "snap" ? 7 : 4,
                    strokeOpacity: collectorMode === "snap" ? 0.54 : 0.46,
                    lineJoin: "round",
                    lineCap: "round",
                    zIndex: collectorMode === "snap" ? 34 : 30
                });
                roadLine.on("rightclick", function (event) {
                    if (finishDrawingFromOverlay(event, "右键结束连续打点，正在保存道路。")) {
                        return;
                    }
                    consumeMapEvent(event);
                    deleteSavedRoad(edge).catch(function (error) { status(error.message); });
                });
                roadLine.on("click", function (event) {
                    if (collectorMode !== "snap") {
                        return;
                    }
                    consumeMapEvent(event);
                    suppressNextClick = true;
                    const screenPoint = event && event.originEvent
                        ? mapLocalPoint(event.originEvent)
                        : pointToContainer(eventPoint(event));
                    const closestRoad = nearestRoadEndpointOnEdgeFromScreen(edge, screenPoint)
                        || (screenPoint ? nearestRoadEndpointFromScreen(screenPoint) : null);
                    if (closestRoad) {
                        selectSnapEndpoint(closestRoad.endpoint).catch(function (error) { status(error.message); });
                    } else {
                        status("吸附模式：请更靠近道路折点点击，或先点路线点让附近路节点显示。");
                    }
                });
                return roadLine;
            }

            function linkEndpointPoint(ref) {
                if (!ref) {
                    return null;
                }
                if (ref.type === "poi") {
                    return poiPointById(ref.id);
                }
                if (ref.type === "facility") {
                    return facilityPointById(ref.id);
                }
                if (ref.type === "road") {
                    return roadPointByRef(ref);
                }
                return null;
            }

            function savedLinkPath(link) {
                if (link.amap_geometry && link.amap_geometry.length >= 2) {
                    return link.amap_geometry.map(function (point) {
                        return [Number(point[0]), Number(point[1])];
                    });
                }
                const aPoint = linkEndpointPoint(link.a);
                const bPoint = linkEndpointPoint(link.b);
                return aPoint && bPoint ? [aPoint, bPoint] : [];
            }

            function snapLinkPayload() {
                return {
                    road_type: "connector",
                    walk: true,
                    bike: true,
                    congestion: 0.82
                };
            }

            function endpointDistance(a, b) {
                const aPoint = endpointPoint(a);
                const bPoint = endpointPoint(b);
                if (!aPoint || !bPoint) {
                    return Infinity;
                }
                return haversine(aPoint[1], aPoint[0], bPoint[1], bPoint[0]);
            }

            async function snapFacilityToRoad(facilityEndpoint, roadEndpoint) {
                const facility = facilityById(facilityEndpoint.id);
                const nearestNode = roadGraphNodeId(roadEndpoint);
                if (!facility || !nearestNode) {
                    throw new Error("场所或道路节点无效，无法吸附。");
                }
                const payload = await requestCollector("/api/collector/facility", {
                    method: "POST",
                    body: JSON.stringify({
                        ...facility,
                        nearest_node: nearestNode
                    })
                });
                return payload;
            }

            async function autoSnapSelectedEndpoints() {
                return autoSnapSelectedEndpointsOptimized();
                if (selectedSnapEndpoints.length !== 2) {
                    return false;
                }
                const first = selectedSnapEndpoints[0];
                const second = selectedSnapEndpoints[1];
                const types = [first.type, second.type].sort();
                const distance = endpointDistance(first, second);
                if (distance > maxSnapDistanceMeters) {
                    status(`两个端点相距约 ${Math.round(distance)} 米，超过 ${maxSnapDistanceMeters} 米，未吸附。请选更近的端点。`);
                    selectedSnapEndpoints = [];
                    selectedSavedRoadPoint = null;
                    selectedPoiTarget = null;
                    redrawSnapSelectionHighlights();
                    return false;
                }
                if (types[0] === "poi" && types[1] === "poi") {
                    status("路线点不能直接吸附路线点，请把每个路线点分别接入附近道路节点。");
                    selectedSnapEndpoints = [];
                    redrawSnapSelectionHighlights();
                    return false;
                }
                if (types.indexOf("road") === -1) {
                    status("吸附必须至少包含一个路节点。场所和路线点需要接到道路上。");
                    selectedSnapEndpoints = [];
                    redrawSnapSelectionHighlights();
                    return false;
                }

                pushUndoSnapshot();
                const label = `${endpointLabel(first)} ↔ ${endpointLabel(second)}`;
                if (types[0] === "facility" || types[1] === "facility") {
                    const facilityEndpoint = first.type === "facility" ? first : second;
                    const roadEndpoint = first.type === "road" ? first : second;
                    await snapFacilityToRoad(facilityEndpoint, roadEndpoint);
                } else {
                    await requestCollector("/api/collector/link", {
                        method: "POST",
                        body: JSON.stringify({
                            a: first,
                            b: second,
                            ...snapLinkPayload()
                        })
                    });
                }
                selectedSnapEndpoints = [];
                selectedSavedRoadPoint = null;
                selectedPoiTarget = null;
                redrawSnapSelectionHighlights();
                await refreshCollector();
                status(`已吸附：${label}。如误连，请点击“撤销上步”。`);
                return true;
            }

            async function autoSnapSelectedEndpointsOptimized() {
                if (selectedSnapEndpoints.length !== 2) {
                    return false;
                }
                const first = selectedSnapEndpoints[0];
                const second = selectedSnapEndpoints[1];
                const types = [first.type, second.type].sort();
                const distance = endpointDistance(first, second);
                if (distance > maxSnapDistanceMeters) {
                    status(`两个端点相距约 ${Math.round(distance)} 米，超过 ${maxSnapDistanceMeters} 米，未吸附。请选更近的端点。`);
                    selectedSnapEndpoints = [];
                    selectedSavedRoadPoint = null;
                    selectedPoiTarget = null;
                    redrawSnapSelectionHighlights();
                    return false;
                }
                if (types[0] === "poi" && types[1] === "poi") {
                    status("路线点不能直接吸附路线点，请把每个路线点分别接入附近道路节点。");
                    selectedSnapEndpoints = [];
                    redrawSnapSelectionHighlights();
                    return false;
                }
                if (types.indexOf("road") === -1) {
                    status("吸附必须至少包含一个路节点。场所和路线点需要接到道路上。");
                    selectedSnapEndpoints = [];
                    redrawSnapSelectionHighlights();
                    return false;
                }

                pushUndoSnapshot();
                const label = `${endpointLabel(first)} ↔ ${endpointLabel(second)}`;
                if (types[0] === "facility" || types[1] === "facility") {
                    const facilityEndpoint = first.type === "facility" ? first : second;
                    const roadEndpoint = first.type === "road" ? first : second;
                    const payload = await snapFacilityToRoad(facilityEndpoint, roadEndpoint);
                    if (payload && payload.facility) {
                        collectorState.facilities = (collectorState.facilities || []).filter(function (item) {
                            return String(item.id) !== String(payload.facility.id);
                        }).concat(payload.facility);
                    }
                } else {
                    const payload = await requestCollector("/api/collector/link", {
                        method: "POST",
                        body: JSON.stringify({
                            a: first,
                            b: second,
                            ...snapLinkPayload()
                        })
                    });
                    if (payload && payload.link) {
                        collectorState.links = (collectorState.links || []).filter(function (item) {
                            return String(item.id) !== String(payload.link.id);
                        }).concat(payload.link);
                    }
                }
                selectedSnapEndpoints = [];
                selectedSavedRoadPoint = null;
                selectedPoiTarget = null;
                rebuildCollectorLookupCaches();
                collectorRoadPointCacheDirty = true;
                redrawSavedV2();
                redrawSnapSelectionHighlights();
                status(`已吸附：${label}。如需修改可直接用撤销上步。`);
                return true;
            }

            function attachedPoiFor(index) {
                return pointPoiLinks.find(function (link) { return link.index === index; });
            }

            function attachedRoadFor(index) {
                return pointRoadLinks.find(function (link) { return link.index === index; });
            }

            function cleanupPointLinks() {
                pointPoiLinks = pointPoiLinks.filter(function (link) {
                    return link.index >= 0 && link.index < editPoints.length;
                });
                pointRoadLinks = pointRoadLinks.filter(function (link) {
                    return link.index >= 0 && link.index < editPoints.length;
                });
                editBreaks = Array.from(new Set(editBreaks.filter(function (index) {
                    return index >= 0 && index < editPoints.length - 1;
                }))).sort(function (a, b) { return a - b; });
            }

            function deleteEditPoint(index) {
                if (index < 0 || index >= editPoints.length) {
                    return;
                }
                pushEditorHistory();
                const oldLength = editPoints.length;
                const removed = index + 1;
                editPoints.splice(index, 1);
                editBreaks = editBreaks
                    .filter(function (breakIndex) { return breakIndex !== index; })
                    .map(function (breakIndex) { return breakIndex > index ? breakIndex - 1 : breakIndex; });
                if (index > 0 && index < oldLength - 1) {
                    editBreaks.push(index - 1);
                }
                pointPoiLinks = pointPoiLinks
                    .filter(function (link) { return link.index !== index; })
                    .map(function (link) {
                        return link.index > index
                            ? { index: link.index - 1, poi: link.poi }
                            : link;
                    });
                pointRoadLinks = pointRoadLinks
                    .filter(function (link) { return link.index !== index; })
                    .map(function (link) {
                        return link.index > index
                            ? { index: link.index - 1, edge: link.edge, target_index: link.target_index }
                            : link;
                    });
                selectedEditIndex = -1;
                redrawEditor();
                status(`已删除第 ${removed} 个路节点；保存后该处会断开成两段道路。`);
            }

            async function deleteSavedPoi(node) {
                if (!node || collectorMode === "snap" || rightDrawing) {
                    return;
                }
                if (!window.confirm(`删除路线点「${node.name}」吗？相关吸附连接也会移除。`)) {
                    return;
                }
                pushUndoSnapshot();
                await requestCollector(`/api/collector/node/${encodeURIComponent(node.id)}`, { method: "DELETE" });
                collectorState.nodes = (collectorState.nodes || []).filter(function (item) {
                    return String(item.id) !== String(node.id);
                });
                collectorState.links = (collectorState.links || []).filter(function (link) {
                    const a = link.a || {};
                    const b = link.b || {};
                    return !(String(a.id) === String(node.id) || String(b.id) === String(node.id));
                });
                selectedPoiTarget = null;
                selectedSnapEndpoints = [];
                rebuildCollectorLookupCaches();
                collectorRoadPointCacheDirty = true;
                redrawSavedV2();
                status(`已删除路线点「${node.name}」。`);
            }

            async function deleteSavedFacility(facility) {
                if (!facility || rightDrawing) {
                    return;
                }
                if (!window.confirm(`删除场所「${facility.name}」吗？该场所不会再参与模块三查询。`)) {
                    return;
                }
                pushUndoSnapshot();
                await requestCollector(`/api/collector/facility/${encodeURIComponent(facility.id)}`, { method: "DELETE" });
                collectorState.facilities = (collectorState.facilities || []).filter(function (item) {
                    return String(item.id) !== String(facility.id);
                });
                rebuildCollectorLookupCaches();
                collectorRoadPointCacheDirty = true;
                redrawSavedV2();
                status(`已删除场所「${facility.name}」。`);
            }

            async function renameSavedPoi(node) {
                if (!node || rightDrawing) {
                    return;
                }
                const nextName = window.prompt("请输入新的路线点名称", node.name || "");
                if (nextName === null) {
                    return;
                }
                const name = nextName.trim();
                if (!name || name === node.name) {
                    return;
                }
                pushUndoSnapshot();
                const payload = await requestCollector("/api/collector/node", {
                    method: "POST",
                    body: JSON.stringify({ ...node, name })
                });
                collectorState.nodes = (collectorState.nodes || []).filter(function (item) {
                    return String(item.id) !== String(payload.node.id);
                }).concat(payload.node);
                rebuildCollectorLookupCaches();
                collectorRoadPointCacheDirty = true;
                redrawSavedV2();
                status(`已将路线点重命名为「${payload.node.name}」。`);
            }

            async function renameSavedFacility(facility) {
                if (!facility || rightDrawing) {
                    return;
                }
                const nextName = window.prompt("请输入新的场所名称", facility.name || "");
                if (nextName === null) {
                    return;
                }
                const name = nextName.trim();
                if (!name || name === facility.name) {
                    return;
                }
                pushUndoSnapshot();
                const payload = await requestCollector("/api/collector/facility", {
                    method: "POST",
                    body: JSON.stringify({ ...facility, name })
                });
                collectorState.facilities = (collectorState.facilities || []).filter(function (item) {
                    return String(item.id) !== String(payload.facility.id);
                }).concat(payload.facility);
                rebuildCollectorLookupCaches();
                collectorRoadPointCacheDirty = true;
                redrawSavedV2();
                status(`已将场所重命名为「${payload.facility.name}」。`);
            }
            async function deleteSavedRoad(edge) {
                if (!edge || collectorMode === "snap" || rightDrawing) {
                    return;
                }
                if (!window.confirm(`删除整条道路「${edge.name || edge.id}」吗？相关吸附连接也会移除。`)) {
                    return;
                }
                pushUndoSnapshot();
                await requestCollector(`/api/collector/edge/${encodeURIComponent(edge.id)}`, { method: "DELETE" });
                collectorState.edges = (collectorState.edges || []).filter(function (item) {
                    return String(item.id) !== String(edge.id);
                });
                collectorState.links = (collectorState.links || []).filter(function (link) {
                    const a = link.a || {};
                    const b = link.b || {};
                    return !(
                        (String(a.type) === "road" && String(a.edge) === String(edge.id))
                        || (String(b.type) === "road" && String(b.edge) === String(edge.id))
                    );
                });
                selectedSavedRoadPoint = null;
                selectedSnapEndpoints = [];
                rebuildCollectorLookupCaches();
                collectorRoadPointCacheDirty = true;
                redrawSavedV2();
                status(`已删除道路「${edge.name || edge.id}」。`);
            }

            async function deleteSavedRoadPoint(edge, pointIndex) {
                if (!edge || collectorMode === "snap" || rightDrawing) {
                    return;
                }
                if (!window.confirm(`删除道路「${edge.name || edge.id}」的第 ${pointIndex + 1} 个路节点吗？该道路会在此处断开。`)) {
                    return;
                }
                pushUndoSnapshot();
                await requestCollector(`/api/collector/edge/${encodeURIComponent(edge.id)}/point/${encodeURIComponent(pointIndex)}`, { method: "DELETE" });
                selectedSavedRoadPoint = null;
                selectedSnapEndpoints = [];
                await refreshCollector();
                status(`已删除道路「${edge.name || edge.id}」的第 ${pointIndex + 1} 个路节点。`);
            }

            function redrawSaved() {
                removeOverlayList(savedOverlays);
                (collectorState.edges || []).forEach(function (edge) {
                    if (!edge.amap_geometry || edge.amap_geometry.length < 2) {
                        return;
                    }
                    const roadLine = new AMap.Polyline({
                        path: edge.amap_geometry,
                        strokeColor: "#8aaed8",
                        strokeWeight: 4,
                        strokeOpacity: 0.46,
                        lineJoin: "round",
                        lineCap: "round",
                        zIndex: 30
                    });
                    roadLine.on("rightclick", function (event) {
                        if (finishDrawingFromOverlay(event, "右键结束连续打点，正在保存道路。")) {
                            return;
                        }
                        consumeMapEvent(event);
                        deleteSavedRoad(edge).catch(function (error) { status(error.message); });
                    });
                    savedOverlays.push(roadLine);
                    (edge.poi_links || []).forEach(function (link) {
                        const fromPoint = edge.amap_geometry[link.index];
                        addSnapLine(savedOverlays, fromPoint, poiPointById(link.poi), false);
                    });
                    (edge.road_links || []).forEach(function (link) {
                        const fromPoint = edge.amap_geometry[link.index];
                        addSnapLine(savedOverlays, fromPoint, roadPointByLink(link), false);
                    });
                    edge.amap_geometry.forEach(function (point, pointIndex) {
                        const isSelected = selectedSavedRoadPoint
                            && selectedSavedRoadPoint.edge === edge.id
                            && selectedSavedRoadPoint.target_index === pointIndex;
                    const marker = new AMap.Marker({
                        position: point,
                        content: `<button type="button" class="saved-road-dot ${isSelected ? "is-selected" : ""}" title="${htmlEscape(edge.name || edge.id)} 第 ${pointIndex + 1} 个路点" aria-label="选择已保存道路路点"></button>`,
                        anchor: "center",
                        zIndex: isSelected ? 112 : 38
                    });
                    marker.on("click", function (event) {
                        if (event && event.originEvent && event.originEvent.stopPropagation) {
                            event.originEvent.stopPropagation();
                        }
                        suppressNextClick = true;
                        selectedSavedRoadPoint = { edge: edge.id, target_index: pointIndex, name: edge.name || edge.id };
                        redrawSaved();
                        redrawEditor();
                        status(selectedEditIndex >= 0 && selectedEditIndex < editPoints.length
                            ? "当前道路还未保存。请先保存道路，再吸附已保存的小圆路点。"
                            : "吸附模式：已选中已保存道路小圆点。继续点击另一个相近端点即可自动连接。");
                    });
                        savedOverlays.push(marker);
                    });
                });
                (collectorState.nodes || []).forEach(function (node) {
                    const isSelectedPoi = selectedPoiTarget && selectedPoiTarget.id === node.id;
                    const marker = new AMap.Marker({
                        position: [Number(node.amap_lng), Number(node.amap_lat)],
                        content: `<button type="button" class="route-point-map-marker collector-route-point-map-marker is-selected ${isSelectedPoi ? "is-link-target" : ""}" aria-label="选择 POI ${htmlEscape(node.name)}"><span class="route-point-map-dot"></span><span class="route-point-map-label">${htmlEscape(node.name)}</span></button>`,
                        anchor: "center",
                        zIndex: isSelectedPoi ? 118 : 105
                    });
                    marker.on("click", function (event) {
                        if (event && event.originEvent && event.originEvent.stopPropagation) {
                            event.originEvent.stopPropagation();
                        }
                        suppressNextClick = true;
                        selectedPoiTarget = { id: node.id, name: node.name };
                        redrawSaved();
                        redrawEditor();
                        status(selectedEditIndex >= 0 && selectedEditIndex < editPoints.length
                            ? `路线点「${node.name}」已选中；请先保存当前道路，再进行吸附。`
                            : `吸附模式：已选中路线点「${node.name}」。继续点击相近路节点即可自动连接。`);
                    });
                    savedOverlays.push(marker);
                });
                if (savedOverlays.length) {
                    map.add(savedOverlays);
                }
                redrawSnapSelectionHighlights();
            }

            function redrawSavedV2() {
                return redrawSavedV2Optimized();
                removeOverlayList(savedOverlays);
                savedTransientOverlays.length = 0;
                rebuildCollectorRoadPointCache();
                let renderedRoadMarkerCount = 0;
                const roadMarkerBudget = collectorMode === "snap"
                    ? maxVisibleSnapRoadMarkers
                    : maxVisibleSnapRoadMarkers * 2;
                let renderedNamedMarkerCount = 0;
                const namedMarkerBudget = 650;
                (collectorState.edges || []).forEach(function (edge) {
                    if (!edge.amap_geometry || edge.amap_geometry.length < 2) {
                        return;
                    }
                    if (!pathTouchesViewport(edge.amap_geometry)) {
                        return;
                    }
                    savedOverlays.push(new AMap.Polyline({
                        path: edge.amap_geometry,
                        strokeColor: "#8aaed8",
                        strokeWeight: 4,
                        strokeOpacity: 0.46,
                        lineJoin: "round",
                        lineCap: "round",
                        zIndex: 30
                    }));
                    edge.amap_geometry.forEach(function (point, pointIndex) {
                        const endpoint = { type: "road", edge: edge.id, point_index: pointIndex, name: edge.name || edge.id };
                        const isSelected = snapEndpointSelected(endpoint);
                        const isFocus = !isSelected && isCollectorRoadFocusPoint(point);
                        if (!isSelected && !isFocus && renderedRoadMarkerCount >= roadMarkerBudget) {
                            return;
                        }
                        if (!shouldRenderSavedRoadPoint(point, isSelected)) {
                            return;
                        }
                        if (!isFocus) {
                            renderedRoadMarkerCount += 1;
                        }
                        const marker = new AMap.Marker({
                            position: point,
                            content: `<button type="button" class="saved-road-dot ${isSelected ? "is-selected" : ""} ${isFocus ? "collector-snap-focus" : ""}" title="${htmlEscape(edge.name || edge.id)} #${pointIndex + 1}" aria-label="选择已保存道路路点"></button>`,
                            anchor: "center",
                            zIndex: isSelected ? 112 : isFocus ? 92 : 72
                        });
                        marker.on("click", function (event) {
                            if (event && event.originEvent && event.originEvent.stopPropagation) {
                                event.originEvent.stopPropagation();
                            }
                            suppressNextClick = true;
                            if (collectorMode === "snap") {
                                selectSnapEndpoint(endpoint).catch(function (error) { status(error.message); });
                                return;
                            }
                            selectedSnapEndpoints = [];
                            selectedPoiTarget = null;
                            selectedSavedRoadPoint = { edge: edge.id, target_index: pointIndex, name: edge.name || edge.id };
                            status("已选中保存道路上的路节点。切换到吸附模式后可与路线点或其他路节点连接。");
                            redrawSavedV2();
                        });
                        marker.on("rightclick", function (event) {
                            if (finishDrawingFromOverlay(event, "右键结束连续打点，正在保存道路。")) {
                                return;
                            }
                            consumeMapEvent(event);
                            suppressNextClick = true;
                            deleteSavedRoadPoint(edge, pointIndex).catch(function (error) { status(error.message); });
                        });
                        savedOverlays.push(marker);
                        savedTransientOverlays.push(marker);
                    });
                });
                (collectorState.links || []).forEach(function (link) {
                    const path = savedLinkPath(link);
                    if (path.length < 2 || !pathTouchesViewport(path)) {
                        return;
                    }
                    savedOverlays.push(new AMap.Polyline({
                        path,
                        strokeColor: "#f2b15f",
                        strokeWeight: 5,
                        strokeOpacity: 0.9,
                        lineJoin: "round",
                        lineCap: "round",
                        zIndex: 50
                    }));
                });
                (collectorState.nodes || []).forEach(function (node) {
                    const endpoint = { type: "poi", id: node.id, name: node.name };
                    const isSelectedPoi = snapEndpointSelected(endpoint);
                    const poiPoint = [Number(node.amap_lng), Number(node.amap_lat)];
                    if (!isSelectedPoi && renderedNamedMarkerCount >= namedMarkerBudget) {
                        return;
                    }
                    if (!shouldRenderNamedCollectorMarker(poiPoint, isSelectedPoi)) {
                        return;
                    }
                    renderedNamedMarkerCount += 1;
                    const marker = new AMap.Marker({
                        position: poiPoint,
                        content: `<button type="button" class="route-point-map-marker collector-route-point-map-marker is-selected ${isSelectedPoi ? "is-link-target" : ""}" aria-label="选择路线点 ${htmlEscape(node.name)}"><span class="route-point-map-dot"></span><span class="route-point-map-label">${htmlEscape(node.name)}</span></button>`,
                        anchor: "center",
                        zIndex: isSelectedPoi ? 118 : 105
                    });
                    marker.on("click", function (event) {
                        consumeMapEvent(event);
                        suppressNextClick = true;
                        const view = captureMapView();
                        if (collectorMode === "snap") {
                            selectSnapEndpoint(endpoint).catch(function (error) { status(error.message); });
                            restoreMapView(view);
                            return;
                        }
                        selectedPoiTarget = { id: node.id, name: node.name };
                        status(`已选中路线点「${node.name}」。切换到吸附模式后可与道路节点连接。`);
                        redrawSavedV2();
                        restoreMapView(view);
                    });
                    marker.on("dblclick", function (event) {
                        consumeMapEvent(event);
                        suppressNextClick = true;
                        const view = captureMapView();
                        renameSavedPoi(node)
                            .catch(function (error) { status(error.message); })
                            .finally(function () { restoreMapView(view); });
                    });
                    marker.on("rightclick", function (event) {
                        if (finishDrawingFromOverlay(event, "右键结束连续打点，正在保存道路。")) {
                            return;
                        }
                        consumeMapEvent(event);
                        suppressNextClick = true;
                        const view = captureMapView();
                        deleteSavedPoi(node)
                            .catch(function (error) { status(error.message); })
                            .finally(function () { restoreMapView(view); });
                    });
                    savedOverlays.push(marker);
                    savedTransientOverlays.push(marker);
                });
                (collectorState.facilities || []).forEach(function (facility) {
                    const displayName = facilityDisplayName(facility);
                    const typeLabel = facilityTypeLabel(facility);
                    const endpoint = { type: "facility", id: facility.id, name: facility.name };
                    const isSelectedFacility = snapEndpointSelected(endpoint);
                    const facilityPoint = [Number(facility.amap_lng), Number(facility.amap_lat)];
                    if (!isSelectedFacility && renderedNamedMarkerCount >= namedMarkerBudget) {
                        return;
                    }
                    if (!shouldRenderNamedCollectorMarker(facilityPoint, isSelectedFacility)) {
                        return;
                    }
                    renderedNamedMarkerCount += 1;
                    const nearestPoint = graphNodePointById(facility.nearest_node) || nearestCollectorGraphPoint(facilityPoint);
                    if (nearestPoint) {
                        addSnapLine(savedOverlays, facilityPoint, nearestPoint, isSelectedFacility);
                    }
                    const marker = new AMap.Marker({
                        position: facilityPoint,
                        content: `<button type="button" class="facility-map-marker collector-facility-map-marker ${isSelectedFacility ? "is-link-target" : ""}" aria-label="场所 ${htmlEscape(displayName)}"><span class="facility-map-dot"></span><span class="facility-map-label"><strong>${htmlEscape(displayName)}</strong><small>${htmlEscape(typeLabel)}</small></span></button>`,
                        anchor: "center",
                        zIndex: isSelectedFacility ? 118 : 96
                    });
                    marker.on("click", function (event) {
                        consumeMapEvent(event);
                        suppressNextClick = true;
                        const view = captureMapView();
                        if (collectorMode === "snap") {
                            selectSnapEndpoint(endpoint).catch(function (error) { status(error.message); });
                            restoreMapView(view);
                            return;
                        }
                        status(`场所「${displayName}」已绑定到最近图节点 ${facility.nearest_node || "未绑定"}，用于模块三按道路距离查询。`);
                        restoreMapView(view);
                    });
                    marker.on("dblclick", function (event) {
                        consumeMapEvent(event);
                        suppressNextClick = true;
                        const view = captureMapView();
                        renameSavedFacility(facility)
                            .catch(function (error) { status(error.message); })
                            .finally(function () { restoreMapView(view); });
                    });
                    marker.on("rightclick", function (event) {
                        if (finishDrawingFromOverlay(event, "右键结束连续打点，正在保存道路。")) {
                            return;
                        }
                        consumeMapEvent(event);
                        suppressNextClick = true;
                        const view = captureMapView();
                        deleteSavedFacility(facility)
                            .catch(function (error) { status(error.message); })
                            .finally(function () { restoreMapView(view); });
                    });
                    savedOverlays.push(marker);
                    savedTransientOverlays.push(marker);
                });
                if (savedOverlays.length) {
                    map.add(savedOverlays);
                }
            }

            function redrawSavedV2Optimized() {
                removeOverlayList(savedOverlays);
                savedTransientOverlays.length = 0;
                rebuildCollectorRoadPointCache();
                refreshCollectorRoadFocusCache();
                collectorRenderViewportBox = currentViewportBox(0.06);
                const viewportBox = collectorRenderViewportBox;
                const visibleEdgeIds = currentViewportRoadEdgeIds(0.06);
                const visibleEdgeSet = new Set(visibleEdgeIds);
                const visibleNamedItems = currentViewportNamedCollectorItems(0.04);
                const renderRoadMarkers = collectorRoadMarkerRenderEnabled();
                let renderedRoadMarkerCount = 0;
                const roadMarkerBudget = collectorMode === "road" && rightDrawing
                    ? 420
                    : collectorMode === "snap"
                    ? maxVisibleSnapRoadMarkers
                    : maxVisibleSnapRoadMarkers * 2;
                let renderedNamedMarkerCount = 0;
                const namedMarkerBudget = 650;

                (collectorState.edges || []).forEach(function (edge) {
                    if (!visibleEdgeSet.has(String(edge.id))) {
                        return;
                    }
                    const edgeGeometry = edge.amap_geometry || [];
                    if (edgeGeometry.length < 2) {
                        return;
                    }
                    const bounds = collectorEdgeBounds.get(String(edge.id));
                    if (viewportBox && bounds) {
                        const intersects = bounds.east >= viewportBox.west
                            && bounds.west <= viewportBox.east
                            && bounds.north >= viewportBox.south
                            && bounds.south <= viewportBox.north;
                        if (!intersects) {
                            return;
                        }
                    }
                    savedOverlays.push(createSavedRoadPolyline(edge, edgeGeometry));
                    if (!renderRoadMarkers) {
                        return;
                    }
                    edgeGeometry.forEach(function (point, pointIndex) {
                        const endpoint = { type: "road", edge: edge.id, point_index: pointIndex, name: edge.name || edge.id };
                        const isSelected = snapEndpointSelected(endpoint);
                        const isFocus = !isSelected && isCollectorRoadFocusPoint(point);
                        if (!isSelected && !isFocus && renderedRoadMarkerCount >= roadMarkerBudget) {
                            return;
                        }
                        if (!shouldRenderSavedRoadPoint(point, isSelected)) {
                            return;
                        }
                        if (!isFocus) {
                            renderedRoadMarkerCount += 1;
                        }
                        const marker = new AMap.Marker({
                            position: point,
                            content: `<button type="button" class="saved-road-dot ${isSelected ? "is-selected" : ""} ${isFocus ? "collector-snap-focus" : ""}" title="${htmlEscape(edge.name || edge.id)} #${pointIndex + 1}" aria-label="选择已保存道路点"></button>`,
                            anchor: "center",
                            zIndex: isSelected ? 112 : isFocus ? 92 : 72
                        });
                        marker.on("click", function (event) {
                            if (event && event.originEvent && event.originEvent.stopPropagation) {
                                event.originEvent.stopPropagation();
                            }
                            suppressNextClick = true;
                            if (collectorMode === "snap") {
                                selectSnapEndpoint(endpoint).catch(function (error) { status(error.message); });
                                return;
                            }
                            selectedSavedRoadPoint = { edge: edge.id, target_index: pointIndex, name: edge.name || edge.id };
                            status("已选中保存道路上的路节点。切换到吸附模式后可与路线点或场所连接。");
                            redrawSavedV2Optimized();
                        });
                        marker.on("rightclick", function (event) {
                            if (finishDrawingFromOverlay(event, "右键结束连续打点，正在保存道路。")) {
                                return;
                            }
                            consumeMapEvent(event);
                            suppressNextClick = true;
                            deleteSavedRoadPoint(edge, pointIndex).catch(function (error) { status(error.message); });
                        });
                        savedOverlays.push(marker);
                        savedTransientOverlays.push(marker);
                    });
                });

                (collectorState.links || []).forEach(function (link) {
                    const path = savedLinkPath(link);
                    if (path.length < 2 || !pathTouchesViewport(path)) {
                        return;
                    }
                    savedOverlays.push(new AMap.Polyline({
                        path,
                        strokeColor: "#f2b15f",
                        strokeWeight: 5,
                        strokeOpacity: 0.9,
                        lineJoin: "round",
                        lineCap: "round",
                        zIndex: 50
                    }));
                });

                visibleNamedItems.forEach(function (entry) {
                    const item = entry.item;
                    if (!item) {
                        return;
                    }
                    if (entry.kind === "node") {
                        const node = item;
                        const endpoint = { type: "poi", id: node.id, name: node.name };
                        const isSelectedPoi = snapEndpointSelected(endpoint);
                        const poiPoint = [Number(node.amap_lng), Number(node.amap_lat)];
                        if (!isSelectedPoi && renderedNamedMarkerCount >= namedMarkerBudget) {
                            return;
                        }
                        if (!shouldRenderNamedCollectorMarker(poiPoint, isSelectedPoi)) {
                            return;
                        }
                        renderedNamedMarkerCount += 1;
                        const marker = new AMap.Marker({
                            position: poiPoint,
                            content: `<button type="button" class="route-point-map-marker collector-route-point-map-marker is-selected ${isSelectedPoi ? "is-link-target" : ""}" aria-label="选择路线点 ${htmlEscape(node.name)}"><span class="route-point-map-dot"></span><span class="route-point-map-label">${htmlEscape(node.name)}</span></button>`,
                            anchor: "center",
                            zIndex: isSelectedPoi ? 118 : 105
                        });
                        marker.on("click", function (event) {
                            consumeMapEvent(event);
                            suppressNextClick = true;
                            const view = captureMapView();
                            if (collectorMode === "snap") {
                                selectSnapEndpoint(endpoint).catch(function (error) { status(error.message); });
                                restoreMapView(view);
                                return;
                            }
                            selectedSnapEndpoints = [];
                            selectedSavedRoadPoint = null;
                            selectedPoiTarget = { id: node.id, name: node.name };
                            status(`已选中路线点「${node.name}」。切换到吸附模式后可与道路节点连接。`);
                            redrawSavedV2Optimized();
                            restoreMapView(view);
                        });
                        marker.on("dblclick", function (event) {
                            consumeMapEvent(event);
                            suppressNextClick = true;
                            const view = captureMapView();
                            renameSavedPoi(node)
                                .catch(function (error) { status(error.message); })
                                .finally(function () { restoreMapView(view); });
                        });
                        marker.on("rightclick", function (event) {
                            if (finishDrawingFromOverlay(event, "右键结束连续打点，正在保存道路。")) {
                                return;
                            }
                            consumeMapEvent(event);
                            suppressNextClick = true;
                            const view = captureMapView();
                            deleteSavedPoi(node)
                                .catch(function (error) { status(error.message); })
                                .finally(function () { restoreMapView(view); });
                        });
                        savedOverlays.push(marker);
                        savedTransientOverlays.push(marker);
                        return;
                    }
                    if (entry.kind !== "facility") {
                        return;
                    }
                    const facility = item;
                    const displayName = facilityDisplayName(facility);
                    const typeLabel = facilityTypeLabel(facility);
                    const endpoint = { type: "facility", id: facility.id, name: facility.name };
                    const isSelectedFacility = snapEndpointSelected(endpoint);
                    const facilityPoint = [Number(facility.amap_lng), Number(facility.amap_lat)];
                    if (!isSelectedFacility && renderedNamedMarkerCount >= namedMarkerBudget) {
                        return;
                    }
                    if (!shouldRenderNamedCollectorMarker(facilityPoint, isSelectedFacility)) {
                        return;
                    }
                    renderedNamedMarkerCount += 1;
                    const nearestPoint = graphNodePointById(facility.nearest_node) || nearestCollectorGraphPoint(facilityPoint);
                    if (nearestPoint) {
                        addSnapLine(savedOverlays, facilityPoint, nearestPoint, isSelectedFacility);
                    }
                    const marker = new AMap.Marker({
                        position: facilityPoint,
                        content: `<button type="button" class="facility-map-marker collector-facility-map-marker ${isSelectedFacility ? "is-link-target" : ""}" aria-label="场所 ${htmlEscape(displayName)}"><span class="facility-map-dot"></span><span class="facility-map-label"><strong>${htmlEscape(displayName)}</strong><small>${htmlEscape(typeLabel)}</small></span></button>`,
                        anchor: "center",
                        zIndex: isSelectedFacility ? 118 : 96
                    });
                    marker.on("click", function (event) {
                        consumeMapEvent(event);
                        suppressNextClick = true;
                        const view = captureMapView();
                        if (collectorMode === "snap") {
                            selectSnapEndpoint(endpoint).catch(function (error) { status(error.message); });
                            restoreMapView(view);
                            return;
                        }
                        status(`场所「${displayName}」已绑定到最近图节点 ${facility.nearest_node || "暂无"}，用于模块三按道路距离查询。`);
                        restoreMapView(view);
                    });
                    marker.on("dblclick", function (event) {
                        consumeMapEvent(event);
                        suppressNextClick = true;
                        const view = captureMapView();
                        renameSavedFacility(facility)
                            .catch(function (error) { status(error.message); })
                            .finally(function () { restoreMapView(view); });
                    });
                    marker.on("rightclick", function (event) {
                        if (finishDrawingFromOverlay(event, "右键结束连续打点，正在保存道路。")) {
                            return;
                        }
                        consumeMapEvent(event);
                        suppressNextClick = true;
                        const view = captureMapView();
                        deleteSavedFacility(facility)
                            .catch(function (error) { status(error.message); })
                            .finally(function () { restoreMapView(view); });
                    });
                    savedOverlays.push(marker);
                    savedTransientOverlays.push(marker);
                });

                if (savedOverlays.length) {
                    map.add(savedOverlays);
                }
                redrawSnapSelectionHighlights();
                collectorRenderViewportBox = null;
            }

            function appendSavedEdgeToView(edge) {
                if (!edge || !edge.amap_geometry || edge.amap_geometry.length < 2) {
                    return;
                }
                const overlays = [];
                const roadLine = createSavedRoadPolyline(edge, edge.amap_geometry);
                overlays.push(roadLine);
                edge.poi_links = edge.poi_links || [];
                edge.road_links = edge.road_links || [];
                (edge.poi_links || []).forEach(function (link) {
                    const fromPoint = edge.amap_geometry[link.index];
                    addSnapLine(overlays, fromPoint, poiPointById(link.poi), false);
                });
                (edge.road_links || []).forEach(function (link) {
                    const fromPoint = edge.amap_geometry[link.index];
                    addSnapLine(overlays, fromPoint, roadPointByLink(link), false);
                });
                savedOverlays.push(...overlays);
                savedTransientOverlays.push(...overlays);
                map.add(overlays);
                return;
                edge.amap_geometry.forEach(function (point, pointIndex) {
                    const marker = new AMap.Marker({
                        position: point,
                        content: `<button type="button" class="saved-road-dot" title="${htmlEscape(edge.name || edge.id)} #${pointIndex + 1}" aria-label="选择已保存道路路节点"></button>`,
                        anchor: "center",
                        zIndex: 38
                    });
                    marker.on("click", function (event) {
                        if (event && event.originEvent && event.originEvent.stopPropagation) {
                            event.originEvent.stopPropagation();
                        }
                        suppressNextClick = true;
                        if (collectorMode === "snap") {
                            selectSnapEndpoint({ type: "road", edge: edge.id, point_index: pointIndex, name: edge.name || edge.id })
                                .catch(function (error) { status(error.message); });
                            return;
                        }
                        selectedSavedRoadPoint = { edge: edge.id, target_index: pointIndex, name: edge.name || edge.id };
                        redrawSaved();
                        redrawEditor();
                    });
                    marker.on("rightclick", function (event) {
                        if (finishDrawingFromOverlay(event, "右键结束连续打点，正在保存道路。")) {
                            return;
                        }
                        consumeMapEvent(event);
                        suppressNextClick = true;
                        deleteSavedRoadPoint(edge, pointIndex).catch(function (error) { status(error.message); });
                    });
                    overlays.push(marker);
                });
                map.add(overlays);
            }

            redrawSaved = redrawSavedV2;

            let savedRedrawTimer = null;
            let dragPerfSuspended = false;
            function suspendHeavyEditOverlays() {
                if (dragPerfSuspended) {
                    return;
                }
                dragPerfSuspended = true;
                savedTransientOverlays.forEach(function (overlay) {
                    map.remove(overlay);
                });
                editMarkers.forEach(function (overlay) {
                    map.remove(overlay);
                });
            }
            function scheduleSavedRedraw() {
                window.clearTimeout(savedRedrawTimer);
                savedRedrawTimer = window.setTimeout(function () {
                    dragPerfSuspended = false;
                    redrawSavedV2();
                }, 220);
            }
            map.on("dragstart", suspendHeavyEditOverlays);
            map.on("dragend", scheduleSavedRedraw);
            map.on("zoomend", scheduleSavedRedraw);
            map.on("moveend", scheduleSavedRedraw);

            function updateConnectorOptions() {
                return true;
            }

            async function refreshCollector() {
                const payload = await requestCollector("/api/collector/graph");
                collectorState = payload;
                rebuildCollectorLookupCaches();
                collectorRoadPointCacheDirty = true;
                updateConnectorOptions();
                redrawSaved();
                status(`已采集 ${payload.nodes.length} 个路线点，${payload.edges.length} 条道路，${(payload.facilities || []).length} 个场所。正式图：${payload.summary.nodes} 节点 / ${payload.summary.edges} 边。`);
            }

            function redrawEditorGeometry() {
                editLines.forEach(function (line) { map.remove(line); });
                editLines.length = 0;
                editLinkLines.forEach(function (line) { map.remove(line); });
                editLinkLines.length = 0;
                segmentRanges().forEach(function (range) {
                    const path = editPoints.slice(range[0], range[1]);
                    const line = new AMap.Polyline({
                        path,
                        strokeColor: "#d99a55",
                        strokeWeight: 7,
                        strokeOpacity: 0.92,
                        lineJoin: "round",
                        lineCap: "round",
                        zIndex: 119
                    });
                    editLines.push(line);
                    map.add(line);
                });
                pointPoiLinks.forEach(function (link) {
                    addSnapLine(editLinkLines, editPoints[link.index], poiPointById(link.poi), selectedEditIndex === link.index);
                });
                pointRoadLinks.forEach(function (link) {
                    addSnapLine(editLinkLines, editPoints[link.index], roadPointByLink(link), selectedEditIndex === link.index);
                });
                if (editLinkLines.length) {
                    map.add(editLinkLines);
                }
            }

            function redrawEditor() {
                redrawEditorGeometry();
                editMarkers.forEach(function (marker) { map.remove(marker); });
                editMarkers.length = 0;
                if (selectedEditIndex >= editPoints.length) {
                    selectedEditIndex = -1;
                }
                cleanupPointLinks();
                editPoints.forEach(function (point, index) {
                    const link = attachedPoiFor(index);
                    const roadLink = attachedRoadFor(index);
                    const marker = new AMap.Marker({
                        position: point,
                        content: `<button type="button" class="road-editor-dot ${selectedEditIndex === index ? "is-selected" : ""} ${link ? "is-attached" : ""} ${roadLink ? "is-road-attached" : ""}" title="第 ${index + 1} 个道路采样点${link ? "，已吸附到 " + htmlEscape(poiNameById(link.poi)) : ""}${roadLink ? "，已吸附到道路路点" : ""}" aria-label="选择当前道路路点"></button>`,
                        anchor: "center",
                        draggable: true,
                        cursor: "move",
                        zIndex: 120
                    });
                    marker.on("dragstart", function () {
                        pushEditorHistory();
                        draggingEditIndex = index;
                        selectedEditIndex = index;
                        map.setStatus({ dragEnable: false });
                    });
                    marker.on("dragging", function (event) {
                        if (draggingEditIndex !== index || !event || !event.lnglat) {
                            return;
                        }
                        editPoints[index] = [
                            Number(event.lnglat.getLng().toFixed(7)),
                            Number(event.lnglat.getLat().toFixed(7))
                        ];
                        redrawEditorGeometry();
                    });
                    marker.on("dragend", function (event) {
                        if (event && event.lnglat) {
                            editPoints[index] = [
                                Number(event.lnglat.getLng().toFixed(7)),
                                Number(event.lnglat.getLat().toFixed(7))
                            ];
                        }
                        draggingEditIndex = -1;
                        suppressNextClick = true;
                        selectedEditIndex = index;
                        applyMapMotionState();
                        redrawEditor();
                        status("已拖动路节点，整条道路折线已随之变形。");
                    });
                    marker.on("click", function (event) {
                        if (event && event.originEvent && event.originEvent.stopPropagation) {
                            event.originEvent.stopPropagation();
                        }
                        if (suppressNextClick) {
                            suppressNextClick = false;
                            return;
                        }
                        suppressNextClick = true;
                        if (collectorMode !== "snap") {
                            selectedEditIndex = index;
                            redrawEditor();
                            status(`已选中第 ${index + 1} 个道路节点。点击“删选中路点”后，这条未保存道路会在此处断成两段。`);
                            return;
                        }
                        selectedEditIndex = index;
                        redrawEditor();
                        redrawSaved();
                        status("当前道路还未保存。请先保存道路，再在吸附模式中点击已保存的小圆路点进行连接。");
                    });
                    marker.on("rightclick", function (event) {
                        if (finishDrawingFromOverlay(event, "右键结束连续打点，正在保存道路。")) {
                            return;
                        }
                        consumeMapEvent(event);
                        if (collectorMode === "snap" || rightDrawing) {
                            return;
                        }
                        suppressNextClick = true;
                        if (window.confirm(`删除当前未保存道路的第 ${index + 1} 个路节点吗？该道路会在此处断开。`)) {
                            deleteEditPoint(index);
                        }
                    });
                    editMarkers.push(marker);
                });
                if (editMarkers.length) {
                    map.add(editMarkers);
                }
                if (collectorMode === "road") {
                    if (rightDrawing) {
                        status(`连续打点中：移动鼠标沿道路描绘；再次右键或双击结束并保存。当前道路采样点：${editPoints.length}。`);
                    } else if (editPoints.length) {
                        status(`道路采样点：${editPoints.length}。点击小圆路点可选中；右键第二次或双击会结束连续打点并保存。`);
                    }
                }
            }

            async function saveNode(point) {
                pushUndoSnapshot();
                const payload = await requestCollector("/api/collector/node", {
                    method: "POST",
                    body: JSON.stringify({
                        name: nameInput.value || "采集点",
                        category: selectedOptionText(kindInput) || "路线点",
                        tags: selectedOptionText(kindInput) || "",
                        role: "route_point",
                        kind: kindInput.value || "building",
                        amap_lng: point[0],
                        amap_lat: point[1]
                    })
                });
                collectorState.nodes = (collectorState.nodes || []).filter(function (item) {
                    return String(item.id) !== String(payload.node.id);
                }).concat(payload.node);
                collectorState.summary = collectorState.summary || {};
                rebuildCollectorLookupCaches();
                collectorRoadPointCacheDirty = true;
                redrawSavedV2();
                status(`已保存路线点：${payload.node.name}。切换到吸附模式，把它与附近道路节点连接后即可参与路线规划。`);
            }

            async function saveFacility(point) {
                pushUndoSnapshot();
                const facilityType = facilityTypeValue();
                const cuisine = cuisineValue();
                const customTags = (categoryInput.value || "").trim();
                const tagParts = [facilityType, cuisine, customTags].filter(Boolean);
                const payload = await requestCollector("/api/collector/facility", {
                    method: "POST",
                    body: JSON.stringify({
                        name: nameInput.value || "场所",
                        type: facilityType,
                        cuisine,
                        tags: tagParts.join(","),
                        description: cuisine ? `${facilityType} · ${cuisine}，手动采集，按道路图距离排序。` : `${facilityType}，手动采集，按道路图距离排序。`,
                        amap_lng: point[0],
                        amap_lat: point[1]
                    })
                });
                collectorState.facilities = (collectorState.facilities || []).filter(function (item) {
                    return String(item.id) !== String(payload.facility.id);
                }).concat(payload.facility);
                collectorState.summary = collectorState.summary || {};
                rebuildCollectorLookupCaches();
                collectorRoadPointCacheDirty = true;
                redrawSavedV2();
                status(`已保存场所：${payload.facility.name}，最近图节点：${payload.facility.nearest_node || "暂无可绑定节点"}。它用于模块三查询，不出现在路线规划下拉框。`);
            }

            async function saveRoad() {
                stopRightDrawing("连续打点已结束，正在保存道路。");
                const ranges = segmentRanges();
                if (!ranges.length) {
                    status("道路至少需要 2 个连续点。");
                    return;
                }
                pushUndoSnapshot();
                const baseName = nameInput.value || "手动道路";
                const savedEdges = [];
                for (let segmentIndex = 0; segmentIndex < ranges.length; segmentIndex += 1) {
                    const range = ranges[segmentIndex];
                    const start = range[0];
                    const end = range[1];
                    const segmentPoints = editPoints.slice(start, end);
                    const segmentPoiLinks = pointPoiLinks
                        .filter(function (link) { return link.index >= start && link.index < end; })
                        .map(function (link) { return { index: link.index - start, poi: link.poi }; });
                    const segmentRoadLinks = pointRoadLinks
                        .filter(function (link) { return link.index >= start && link.index < end; })
                        .map(function (link) {
                            return { index: link.index - start, edge: link.edge, target_index: link.target_index };
                        });
                    const payload = await requestCollector("/api/collector/edge", {
                        method: "POST",
                        body: JSON.stringify({
                            name: ranges.length > 1 ? `${baseName}-${segmentIndex + 1}` : baseName,
                            from: "",
                            to: "",
                            poi_links: segmentPoiLinks,
                            road_links: segmentRoadLinks,
                            ...roadConfig(),
                            amap_geometry: segmentPoints
                        })
                    });
                    savedEdges.push(payload.edge);
                }
                editPoints = [];
                editBreaks = [];
                pointPoiLinks = [];
                pointRoadLinks = [];
                selectedSavedRoadPoint = null;
                selectedPoiTarget = null;
                selectedEditIndex = -1;
                redrawEditor();
                collectorState.edges = (collectorState.edges || []).concat(savedEdges);
                collectorState.summary = collectorState.summary || {};
                collectorState.summary.edges = collectorState.edges.length;
                rebuildCollectorLookupCaches();
                collectorRoadPointCacheDirty = true;
                redrawSavedV2Optimized();
                redrawSnapSelectionHighlights();
                status(`已保存 ${savedEdges.length} 条道路。删除路节点形成的断口已拆分为独立路段。`);
            }

            function nearestSaved(kind, lng, lat) {
                const list = kind === "edge" ? collectorState.edges || [] : collectorState.nodes || [];
                let best = null;
                list.forEach(function (item) {
                    const point = kind === "edge"
                        ? (item.amap_geometry && item.amap_geometry[0])
                        : [item.amap_lng, item.amap_lat];
                    if (!point) {
                        return;
                    }
                    const distance = haversine(lat, lng, Number(point[1]), Number(point[0]));
                    if (!best || distance < best.distance) {
                        best = { item, distance };
                    }
                });
                return best;
            }

            function mapLocalPoint(event) {
                const rect = mapEl.getBoundingClientRect();
                return {
                    x: Math.max(0, Math.min(rect.width, event.clientX - rect.left)),
                    y: Math.max(0, Math.min(rect.height, event.clientY - rect.top))
                };
            }

            function updateBoxSelectOverlay() {
                const left = Math.min(boxSelect.startX, boxSelect.currentX);
                const top = Math.min(boxSelect.startY, boxSelect.currentY);
                const width = Math.abs(boxSelect.currentX - boxSelect.startX);
                const height = Math.abs(boxSelect.currentY - boxSelect.startY);
                boxSelectOverlay.style.left = `${left}px`;
                boxSelectOverlay.style.top = `${top}px`;
                boxSelectOverlay.style.width = `${width}px`;
                boxSelectOverlay.style.height = `${height}px`;
                boxSelectOverlay.hidden = !boxSelect.active;
            }

            function resetBoxSelect() {
                boxSelect.pressed = false;
                boxSelect.active = false;
                boxSelect.cancelled = false;
                boxSelectOverlay.hidden = true;
                applyMapMotionState();
            }

            function pointToContainer(point) {
                if (!point || !map.lngLatToContainer || !window.AMap) {
                    return null;
                }
                const pixel = map.lngLatToContainer(new AMap.LngLat(Number(point[0]), Number(point[1])));
                if (!pixel) {
                    return null;
                }
                const x = typeof pixel.getX === "function" ? pixel.getX() : pixel.x;
                const y = typeof pixel.getY === "function" ? pixel.getY() : pixel.y;
                return { x: Number(x), y: Number(y) };
            }

            function nearestRoadEndpointFromScreen(screenPoint) {
                rebuildCollectorRoadPointCache();
                const radius = collectorMode === "snap"
                    ? (map.getZoom() >= 18.4 ? 42 : 54)
                    : (map.getZoom() >= 18.4 ? 18 : 24);
                const lnglat = map.containerToLngLat
                    ? map.containerToLngLat(new AMap.Pixel(screenPoint.x, screenPoint.y))
                    : null;
                const point = lnglat
                    ? [lnglat.getLng(), lnglat.getLat()]
                    : null;
                const searchBox = point ? collectorPointBox(point, radius * 2.5) : null;
                const candidates = searchBox
                    ? collectorGridItems(collectorRoadPointGrid, searchBox, null)
                    : rebuildCollectorRoadPointCache();
                let closest = null;
                candidates.forEach(function (item) {
                    if (!item || !item.point) {
                        return;
                    }
                    if (searchBox && !collectorBoxContainsPoint(searchBox, item.point)) {
                        return;
                    }
                    const pixel = pointToContainer(item.point);
                    if (!pixel) {
                        return;
                    }
                    const distance = Math.hypot(pixel.x - screenPoint.x, pixel.y - screenPoint.y);
                    if (distance <= radius && (!closest || distance < closest.distance)) {
                        closest = {
                            endpoint: item.endpoint,
                            point: item.point,
                            distance
                        };
                    }
                });
                return closest;
            }

            function pointInBox(point, box) {
                const pixel = pointToContainer(point);
                return pixel
                    && pixel.x >= box.left
                    && pixel.x <= box.right
                    && pixel.y >= box.top
                    && pixel.y <= box.bottom;
            }

            function screenBoxToGeoBox(box) {
                if (!box || !map.containerToLngLat || !window.AMap) {
                    return null;
                }
                const topLeft = map.containerToLngLat(new AMap.Pixel(box.left, box.top));
                const bottomRight = map.containerToLngLat(new AMap.Pixel(box.right, box.bottom));
                if (!topLeft || !bottomRight) {
                    return null;
                }
                return {
                    west: Math.min(topLeft.getLng(), bottomRight.getLng()),
                    east: Math.max(topLeft.getLng(), bottomRight.getLng()),
                    south: Math.min(topLeft.getLat(), bottomRight.getLat()),
                    north: Math.max(topLeft.getLat(), bottomRight.getLat())
                };
            }

            function selectedItemsInBox(box) {
                const selected = {
                    node_ids: [],
                    facility_ids: [],
                    road_points: []
                };
                rebuildCollectorRoadPointCache();
                const geoBox = screenBoxToGeoBox(box);
                (collectorState.nodes || []).forEach(function (node) {
                    const point = [Number(node.amap_lng), Number(node.amap_lat)];
                    if (geoBox && collectorBoxContainsPoint(geoBox, point)) {
                        selected.node_ids.push(node.id);
                    }
                });
                (collectorState.facilities || []).forEach(function (facility) {
                    const point = [Number(facility.amap_lng), Number(facility.amap_lat)];
                    if (geoBox && collectorBoxContainsPoint(geoBox, point)) {
                        selected.facility_ids.push(facility.id);
                    }
                });
                if (geoBox) {
                    collectorGridItems(collectorRoadPointGrid, geoBox, null).forEach(function (item) {
                        if (collectorBoxContainsPoint(geoBox, item.point)) {
                            selected.road_points.push({
                                edge: item.endpoint.edge,
                                point_index: item.endpoint.point_index
                            });
                        }
                    });
                }
                return selected;
            }

            function selectedCount(selection) {
                return selection.node_ids.length
                    + selection.facility_ids.length
                    + selection.road_points.length;
            }

            async function deleteBoxSelection(selection) {
                const total = selectedCount(selection);
                if (!total) {
                    status("框选范围内没有可删除的采集数据。");
                    return;
                }
                const message = [
                    `路线点 ${selection.node_ids.length} 个`,
                    `场所 ${selection.facility_ids.length} 个`,
                    `路节点 ${selection.road_points.length} 个`
                ].join(" / ");
                if (!window.confirm(`确认删除框选内容吗？\n${message}\n相关吸附连接会自动清理，删除前会写入撤销栈。`)) {
                    status("已取消框选删除。");
                    return;
                }
                pushUndoSnapshot();
                const payload = await requestCollector("/api/collector/batch-delete", {
                    method: "POST",
                    body: JSON.stringify(selection)
                });
                collectorState = payload;
                rebuildCollectorLookupCaches();
                collectorRoadPointCacheDirty = true;
                editPoints = [];
                editBreaks = [];
                pointPoiLinks = [];
                pointRoadLinks = [];
                selectedSavedRoadPoint = null;
                selectedPoiTarget = null;
                selectedSnapEndpoints = [];
                selectedEditIndex = -1;
                clearCollectorOverlayLayers(true);
                redrawEditor();
                redrawSavedV2Optimized();
                const deleted = payload.deleted || {};
                status(`已批量删除：路线点 ${deleted.nodes || 0} 个，场所 ${deleted.facilities || 0} 个，路节点 ${deleted.road_points || 0} 个；相关吸附已清理。`);
            }

            function beginBoxSelect(event) {
                if (event.button !== 0 || rightDrawing || draggingEditIndex >= 0 || collectorMode === "snap") {
                    return;
                }
                if (!mapLocked) {
                    return;
                }
                if (event.target.closest(".road-editor-panel, .route-basemap-switcher, .amap-marker, button, input, select, textarea")) {
                    return;
                }
                const point = mapLocalPoint(event);
                boxSelect.pressed = true;
                boxSelect.active = false;
                boxSelect.startX = point.x;
                boxSelect.startY = point.y;
                boxSelect.currentX = point.x;
                boxSelect.currentY = point.y;
                boxSelect.startedAt = Date.now();
            }

            function moveBoxSelect(event) {
                if (!boxSelect.pressed) {
                    return;
                }
                if (boxSelect.cancelled) {
                    return;
                }
                const point = mapLocalPoint(event);
                boxSelect.currentX = point.x;
                boxSelect.currentY = point.y;
                const distance = Math.hypot(boxSelect.currentX - boxSelect.startX, boxSelect.currentY - boxSelect.startY);
                if (!boxSelect.active) {
                    const elapsed = Date.now() - boxSelect.startedAt;
                    if (distance < 24 || elapsed < 220) {
                        return;
                    }
                    boxSelect.active = true;
                    map.setStatus({ dragEnable: false, doubleClickZoom: false });
                    status("框选删除中：松开鼠标后统计并确认删除。");
                }
                event.preventDefault();
                event.stopPropagation();
                updateBoxSelectOverlay();
            }

            function finishBoxSelect(event) {
                if (!boxSelect.pressed) {
                    return;
                }
                const wasActive = boxSelect.active;
                if (wasActive) {
                    event.preventDefault();
                    event.stopPropagation();
                    const left = Math.min(boxSelect.startX, boxSelect.currentX);
                    const top = Math.min(boxSelect.startY, boxSelect.currentY);
                    const right = Math.max(boxSelect.startX, boxSelect.currentX);
                    const bottom = Math.max(boxSelect.startY, boxSelect.currentY);
                    suppressNextClick = true;
                    resetBoxSelect();
                    if (right - left < 10 || bottom - top < 10) {
                        status("框选范围太小，未执行删除。");
                        return;
                    }
                    deleteBoxSelection(selectedItemsInBox({ left, top, right, bottom }))
                        .catch(function (error) { status(error.message); });
                    return;
                }
                resetBoxSelect();
            }

            panel.addEventListener("click", function (event) {
                const modeButton = event.target.closest("[data-collector-mode]");
                if (modeButton) {
                    collectorMode = modeButton.getAttribute("data-collector-mode");
                    if (collectorMode === "snap") {
                        mapLocked = true;
                    }
                    panel.querySelectorAll("[data-collector-mode]").forEach(function (button) {
                        button.classList.toggle("is-active", button === modeButton);
                    });
                    editPoints = [];
                    editBreaks = [];
                    pointPoiLinks = [];
                    pointRoadLinks = [];
                    selectedSavedRoadPoint = null;
                    selectedPoiTarget = null;
                    selectedSnapEndpoints = [];
                    selectedEditIndex = -1;
                    stopRightDrawing("已切换模式，连续打点结束。");
                    redrawSnapSelectionHighlights();
                    redrawEditor();
                    updateCollectorModeFields();
                    applyMapMotionState();
                    return;
                }
                const button = event.target.closest("[data-editor-action]");
                if (!button) {
                    return;
                }
                const action = button.getAttribute("data-editor-action");
                if (action === "toggle-map-lock") {
                    mapLocked = !mapLocked;
                    applyMapMotionState();
                    if (collectorMode === "snap") {
                        status(mapLocked ? "吸附模式已锁定地图：点选端点更稳定。" : "吸附模式已解锁地图：可以拖动视野。");
                    } else {
                        status(mapLocked ? "道路编辑时地图已锁定：点击只用于采点、选点和吸附。" : "地图已解锁：可以拖动视野；需要精确选点时建议再锁定。");
                    }
                    return;
                }
                if (action === "undo-step") {
                    const snapshot = undoStack.pop();
                    if (!snapshot) {
                        status("暂无可撤销操作。");
                    } else {
                        redoStack.push(collectorSnapshot());
                        restoreCollectorSnapshot(snapshot)
                            .then(function () { status("已撤销上一步操作。"); })
                            .catch(function (error) { status(error.message); });
                    }
                }
                if (action === "redo-step") {
                    const snapshot = redoStack.pop();
                    if (!snapshot) {
                        status("暂无可重做操作。");
                    } else {
                        undoStack.push(collectorSnapshot());
                        restoreCollectorSnapshot(snapshot)
                            .then(function () { status("已重做刚刚撤销的操作。"); })
                            .catch(function (error) { status(error.message); });
                    }
                }
                if (action === "clear") {
                    pushEditorHistory();
                    editPoints = [];
                    editBreaks = [];
                    pointPoiLinks = [];
                    pointRoadLinks = [];
                    selectedEditIndex = -1;
                    selectedSnapEndpoints = [];
                    redrawEditor();
                }
                if (action === "apply-road-preset") {
                    applyRoadPreset();
                }
                if (action === "save-road") {
                    saveRoad().catch(function (error) { status(error.message); });
                }
                if (action === "clear-all") {
                    if (window.confirm("??????????????????????????????????????????")) {
                        stopRightDrawing("??????????????????????");
                        editPoints = [];
                        editBreaks = [];
                        pointPoiLinks = [];
                        pointRoadLinks = [];
                        selectedSavedRoadPoint = null;
                        selectedPoiTarget = null;
                        selectedSnapEndpoints = [];
                        selectedEditIndex = -1;
                        undoStack = [];
                        redoStack = [];
                        clearCollectorOverlayLayers(true);
                        requestCollector("/api/collector/clear", { method: "POST", body: "{}" })
                            .then(function (payload) {
                                collectorState = {
                                    nodes: [],
                                    edges: [],
                                    links: [],
                                    facilities: [],
                                    meta: payload.meta || collectorState.meta || {},
                                    graph: payload.graph || {},
                                    summary: payload.summary || {}
                                };
                                rebuildCollectorLookupCaches();
                                collectorRoadPointCacheDirty = true;
                                removeOverlayList(roadOverlays);
                                removeOverlayList(routeOverlays);
                                removeOverlayList(poiMarkers);
                                removeOverlayList(facilityMarkers);
                                clearCollectorOverlayLayers(true);
                                redrawSnapSelectionHighlights();
                                updateConnectorOptions();
                                redrawEditor();
                                redrawSavedV2();
                                status("?????????????????????????????????????");
                            })
                            .catch(function (error) { status(error.message); });
                    }
                }
            });
            nameInput.addEventListener("input", redrawEditor);
            if (cuisineInput) {
                cuisineInput.addEventListener("change", syncCuisineCustomInput);
            }
            roadTypeInput.addEventListener("change", applyRoadPreset);
            mapEl.addEventListener("mousedown", beginBoxSelect, true);
            document.addEventListener("mousemove", moveBoxSelect);
            document.addEventListener("mouseup", finishBoxSelect);
            mapEl.addEventListener("contextmenu", function (event) {
                if (event.defaultPrevented && !rightDrawing) {
                    return;
                }
                if (collectorMode === "road") {
                    consumeMapEvent(event);
                    if (Date.now() - lastRightActionAt < 300) {
                        return;
                    }
                    lastRightActionAt = Date.now();
                    if (rightDrawing) {
                        finishRightDrawingAndSave("右键结束连续打点，正在保存道路。");
                    } else {
                        startRightDrawing(domEventPoint(event));
                    }
                }
            });

            function eventPoint(event) {
                if (!event || !event.lnglat) {
                    return null;
                }
                return [
                    Number(event.lnglat.getLng().toFixed(7)),
                    Number(event.lnglat.getLat().toFixed(7))
                ];
            }

            function domEventPoint(event) {
                if (!event || !map.containerToLngLat || !window.AMap) {
                    return null;
                }
                const rect = mapEl.getBoundingClientRect();
                const pixel = new AMap.Pixel(event.clientX - rect.left, event.clientY - rect.top);
                const lnglat = map.containerToLngLat(pixel);
                if (!lnglat) {
                    return null;
                }
                return [
                    Number(lnglat.getLng().toFixed(7)),
                    Number(lnglat.getLat().toFixed(7))
                ];
            }

            function isRightMouse(event) {
                const original = event && event.originEvent;
                return original && (original.button === 2 || original.buttons === 2);
            }

            function bearingDegrees(fromPoint, toPoint) {
                if (!fromPoint || !toPoint) {
                    return null;
                }
                const toRad = Math.PI / 180;
                const toDeg = 180 / Math.PI;
                const lat1 = fromPoint[1] * toRad;
                const lat2 = toPoint[1] * toRad;
                const deltaLng = (toPoint[0] - fromPoint[0]) * toRad;
                const y = Math.sin(deltaLng) * Math.cos(lat2);
                const x = Math.cos(lat1) * Math.sin(lat2)
                    - Math.sin(lat1) * Math.cos(lat2) * Math.cos(deltaLng);
                return (Math.atan2(y, x) * toDeg + 360) % 360;
            }

            function bearingDelta(a, b) {
                if (a == null || b == null) {
                    return 0;
                }
                const diff = Math.abs(a - b) % 360;
                return diff > 180 ? 360 - diff : diff;
            }

            function addDragPoint(point) {
                if (!point) {
                    return;
                }
                if (!rightDrawing) {
                    rightDrawing = true;
                }
                const distance = lastDragPoint
                    ? haversine(lastDragPoint[1], lastDragPoint[0], point[1], point[0])
                    : Infinity;
                const nextBearing = lastDragPoint ? bearingDegrees(lastDragPoint, point) : null;
                const turned = bearingDelta(lastDragBearing, nextBearing) >= 12;
                if (lastDragPoint && distance < 3 && !turned) {
                    return;
                }
                pushEditorHistoryIfChanged();
                if (lastDragPoint && distance > 35 && editPoints.length > 0) {
                    editBreaks.push(editPoints.length - 1);
                }
                editPoints.push(point);
                selectedEditIndex = editPoints.length - 1;
                lastDragPoint = point;
                lastDragBearing = nextBearing;
                redrawEditor();
                if (collectorMode === "road") {
                    scheduleSavedRedraw();
                }
            }

            function startRightDrawing(point) {
                if (!point) {
                    status("右键起点无效，请在地图道路位置重新右键。");
                    return;
                }
                lastDragPoint = null;
                lastDragBearing = null;
                addDragPoint(point);
                map.setStatus({ dragEnable: false, doubleClickZoom: false });
                status(`连续打点中：移动鼠标沿道路描绘；再次右键或双击结束并保存。当前道路采样点：${editPoints.length}。`);
            }

            function finishRightDrawingAndSave(message) {
                if (savingRoad) {
                    return;
                }
                if (!rightDrawing && !editPoints.length) {
                    return;
                }
                savingRoad = true;
                stopRightDrawing(message || "连续打点已结束，正在保存道路。");
                saveRoad()
                    .catch(function (error) { status(error.message); })
                    .finally(function () { savingRoad = false; });
            }

            function stopRightDrawing(message) {
                if (!rightDrawing) {
                    return;
                }
                rightDrawing = false;
                suppressNextClick = true;
                lastDragPoint = null;
                lastDragBearing = null;
                applyMapMotionState();
                status(message || `连续打点已结束，当前道路采样点：${editPoints.length}。可继续修点、吸附 POI 或保存道路。`);
            }

            map.on("click", function (event) {
                const point = eventPoint(event);
                if (!point) {
                    return;
                }
                if (rightDrawing) {
                    return;
                }
                if (suppressNextClick) {
                    suppressNextClick = false;
                    return;
                }
                if (collectorMode === "poi") {
                    saveNode(point).catch(function (error) { status(error.message); });
                    return;
                }
                if (collectorMode === "facility") {
                    saveFacility(point).catch(function (error) { status(error.message); });
                    return;
                }
                if (collectorMode === "snap") {
                    const screenPoint = event.originEvent
                        ? mapLocalPoint(event.originEvent)
                        : pointToContainer(point);
                    const closestRoad = screenPoint ? nearestRoadEndpointFromScreen(screenPoint) : null;
                    if (closestRoad) {
                        selectSnapEndpoint(closestRoad.endpoint).catch(function (error) { status(error.message); });
                        return;
                    }
                    status("吸附模式：请点击路线点、场所，或靠近道路节点的位置；大图下不再渲染全部路点，以保持采集流畅。");
                    return;
                }
                addEditPoint(point);
            });
            map.on("rightclick", function (event) {
                if (collectorMode !== "road") {
                    return;
                }
                if (Date.now() - lastRightActionAt < 300) {
                    return;
                }
                lastRightActionAt = Date.now();
                if (event.originEvent && event.originEvent.preventDefault) {
                    event.originEvent.preventDefault();
                }
                if (rightDrawing) {
                    finishRightDrawingAndSave("右键结束连续打点，正在保存道路。");
                    return;
                }
                startRightDrawing(eventPoint(event));
            });
            map.on("mousemove", function (event) {
                if (!rightDrawing || collectorMode !== "road") {
                    return;
                }
                if (event.originEvent && event.originEvent.preventDefault) {
                    event.originEvent.preventDefault();
                }
                addDragPoint(eventPoint(event));
            });
            map.on("dblclick", function () {
                if (collectorMode === "road") {
                    finishRightDrawingAndSave("双击结束连续打点，正在保存道路。");
                }
            });
            mapEl.addEventListener("dblclick", function (event) {
                if (collectorMode !== "road" || !rightDrawing) {
                    return;
                }
                consumeMapEvent(event);
                finishRightDrawingAndSave("双击结束连续打点，正在保存道路。");
            });
            applyMapMotionState();
            updateCollectorModeFields();
            refreshCollector().catch(function (error) { status(error.message); });
            return true;
        }

        const roadEditorActive = setupCollector();

        map.on("click", function (event) {
            if (roadEditorActive) {
                return;
            }
            const lng = event.lnglat.getLng();
            const lat = event.lnglat.getLat();
            const closest = nearestSelectable(lng, lat);
            if (foodPickMode) {
                if (closest && closest.distance <= routeClickRadiusForZoom()) {
                    openFoodsFromOrigin(closest.node.id);
                }
                return;
            }
            if (closest
                && closest.distance <= routeClickRadiusForZoom()
                && shouldShowPlanningNode(closest.node, planningTargetInfo(closest.node.id))) {
                openNodePopup(closest.node);
            }
        });

        map.on("rightclick", handleRouteMapRightClick);

        if (selectedTargetsEl) {
            selectedTargetsEl.addEventListener("click", function (event) {
                const button = event.target.closest("[data-remove-target]");
                if (!button) {
                    return;
                }
                setRouteMode(routeTypeSelect && routeTypeSelect.value === "round_trip" ? "round_trip" : "multi");
                setTargetValue(button.getAttribute("data-remove-target"), false);
                submitPlanner();
            });
        }

        if (clearTargetsButton) {
            clearTargetsButton.addEventListener("click", function () {
                if (!currentStartId() && !currentEndId() && !selectedTargets.size) {
                    return;
                }
                clearAllRoutePoints();
                submitPlanner();
            });
        }

        function findTargetMatch(query) {
            const normalized = (query || "").trim().toLowerCase();
            if (!normalized) {
                return null;
            }
            const exact = selectableNodes.find(function (node) {
                return String(node.id).toLowerCase() === normalized
                    || (node.name || "").toLowerCase() === normalized;
            });
            if (exact) {
                return exact;
            }
            return selectableNodes.find(function (node) {
                return (node.name || "").toLowerCase().includes(normalized);
            }) || null;
        }

        function addTargetFromSearch() {
            if (!poiSearch) {
                return;
            }
            const match = findTargetMatch(poiSearch.value);
            if (!match) {
                return;
            }
            ensureWaypointRouteMode();
            if (setTargetValue(match.id, true)) {
                submitPlanner();
            }
            poiSearch.value = "";
        }

        if (poiSearch) {
            poiSearch.addEventListener("keydown", function (event) {
                if (event.key !== "Enter") {
                    return;
                }
                event.preventDefault();
                addTargetFromSearch();
            });
            poiSearch.addEventListener("change", addTargetFromSearch);
        }

        if (selectedTargetsEl || targetInputsEl) {
            refreshSelectedTargets();
        }

        [startSelect, endSelect].forEach(function (select) {
            if (!select) {
                return;
            }
            select.addEventListener("change", function () {
                refreshSelectedTargets();
                refreshEndpointSearchControls();
            });
        });

        function syncMode() {
            const isMulti = routeTypeSelect && routeTypeSelect.value !== "single";
            if (multiPanel) {
                multiPanel.classList.toggle("is-active", isMulti);
            }
            if (endSelect) {
                endSelect.disabled = false;
                endSelect.closest("label")?.classList.toggle("is-multi-target-end", isMulti);
            }
        }

        if (routeTypeSelect) {
            routeTypeSelect.addEventListener("change", syncMode);
            syncMode();
        }

        if (form) {
            form.addEventListener("change", function (event) {
                if (event.target.matches("select")) {
                    window.clearTimeout(form._routeSubmitTimer);
                    form._routeSubmitTimer = window.setTimeout(function () {
                        form.requestSubmit();
                    }, 280);
                }
            });
        }

        window.addEventListener("resize", function () {
            map.resize();
            if (!routeGeometry.length && campusLimit && !collectMode) {
                map.setBounds(campusLimit);
            }
        });
    });
}());
