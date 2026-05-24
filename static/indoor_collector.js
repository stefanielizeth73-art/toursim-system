(function () {
    document.addEventListener("DOMContentLoaded", function () {
        const NS = "http://www.w3.org/2000/svg";
        const svg = document.getElementById("indoorCollectorMap");
        const floorSelect = document.getElementById("collectorFloor");
        const typeSelect = document.getElementById("collectorNodeType");
        const coreField = document.getElementById("collectorCoreField");
        const coreSelect = document.getElementById("collectorCoreId");
        const nameInput = document.getElementById("collectorNodeName");
        const roadNameInput = document.getElementById("collectorRoadName");
        const roadTypeSelect = document.getElementById("collectorRoadType");
        const statusEl = document.getElementById("indoorCollectorStatus");
        const summaryEl = document.getElementById("indoorCollectorSummary");
        const exportEl = document.getElementById("indoorCollectorExport");
        const floorTitle = document.getElementById("collectorFloorTitle");
        const hintEl = document.getElementById("collectorModeHint");
        const data = window.indoorCollectorData || {};
        const endpoints = window.indoorCollectorEndpoints || {};

        let mode = "node";
        let editPoints = [];
        let rightDrawing = false;
        let selectedSnapEndpoints = [];
        let lastDragPoint = null;
        let undoStack = [];
        let redoStack = [];

        if (!svg || !floorSelect) {
            return;
        }

        const modeHints = {
            node: "左键在底图上添加房间门、电梯、步梯或入口关键点；电梯/步梯可选择跨层核心筒编号。",
            road: "左键逐点绘制道路；右键开始连续打点，移动鼠标采样，再次右键或双击保存。",
            snap: "依次点击一个关键点和一个道路点，或两个道路点，系统会保存吸附连接。"
        };
        const defaultCoreByType = {
            elevator: "west_elevator",
            stairs: "northwest_stairs"
        };

        function floorKey() {
            return String(floorSelect.value || "1");
        }

        function floorPayload(key) {
            data.floors = data.floors || {};
            data.floors[key] = data.floors[key] || { nodes: [], edges: [], links: [] };
            data.floors[key].nodes = data.floors[key].nodes || [];
            data.floors[key].edges = data.floors[key].edges || [];
            data.floors[key].links = data.floors[key].links || [];
            return data.floors[key];
        }

        function clone(value) {
            return JSON.parse(JSON.stringify(value));
        }

        function status(message) {
            if (statusEl) {
                statusEl.textContent = message;
            }
        }

        function updateSummary(summary) {
            if (!summaryEl) {
                return;
            }
            if (summary) {
                summaryEl.textContent = `${summary.manual_nodes || 0} 个关键点，${summary.manual_edges || 0} 条道路，${summary.links || 0} 个吸附`;
                return;
            }
            let nodes = 0;
            let edges = 0;
            let links = 0;
            Object.keys(data.floors || {}).forEach(function (key) {
                const floor = floorPayload(key);
                nodes += floor.nodes.length;
                edges += floor.edges.length;
                links += floor.links.length;
            });
            summaryEl.textContent = `${nodes} 个关键点，${edges} 条道路，${links} 个吸附`;
        }

        function updateExport() {
            if (exportEl) {
                exportEl.value = JSON.stringify(data, null, 2);
            }
        }

        function requestJson(url, options) {
            const config = typeof options === "object" && options.method
                ? options
                : {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(options || {})
                };
            return fetch(url, config).then(function (response) {
                return response.json().then(function (body) {
                    if (!response.ok || body.error) {
                        throw new Error(body.error || "请求失败");
                    }
                    return body;
                });
            });
        }

        function deleteJson(url) {
            return requestJson(url, { method: "DELETE" });
        }

        function svgPoint(event) {
            const point = svg.createSVGPoint();
            point.x = event.clientX;
            point.y = event.clientY;
            const matrix = svg.getScreenCTM();
            if (!matrix) {
                return null;
            }
            const mapped = point.matrixTransform(matrix.inverse());
            return [Number(mapped.x.toFixed(1)), Number(mapped.y.toFixed(1))];
        }

        function pointDistance(a, b) {
            return Math.hypot(Number(a[0]) - Number(b[0]), Number(a[1]) - Number(b[1]));
        }

        function pointsAttr(points) {
            return points.map(function (point) {
                return `${point[0]},${point[1]}`;
            }).join(" ");
        }

        function pushUndo() {
            undoStack.push(clone(data));
            if (undoStack.length > 40) {
                undoStack.shift();
            }
            redoStack = [];
        }

        function restoreSnapshot(snapshot, message) {
            return requestJson(endpoints.restore, snapshot).then(function (payload) {
                Object.keys(data).forEach(function (key) {
                    delete data[key];
                });
                Object.assign(data, clone(snapshot));
                updateSummary(payload.summary);
                render();
                status(message);
            }).catch(function (error) {
                status(error.message);
            });
        }

        function endpointKey(endpoint) {
            if (!endpoint) {
                return "";
            }
            if (endpoint.type === "node") {
                return `node:${endpoint.id}`;
            }
            return `road:${endpoint.edge}:${endpoint.point_index}`;
        }

        function endpointLabel(endpoint) {
            const floor = floorPayload(floorKey());
            if (endpoint.type === "node") {
                const node = floor.nodes.find(function (item) {
                    return String(item.id) === String(endpoint.id);
                });
                return node ? (node.name || node.id) : "关键点";
            }
            const edge = floor.edges.find(function (item) {
                return String(item.id) === String(endpoint.edge);
            });
            return `${edge ? (edge.name || edge.id) : "道路"} #${Number(endpoint.point_index) + 1}`;
        }

        function endpointPoint(endpoint) {
            const floor = floorPayload(floorKey());
            if (endpoint.type === "node") {
                const node = floor.nodes.find(function (item) {
                    return String(item.id) === String(endpoint.id);
                });
                return node ? [node.x, node.y] : null;
            }
            const edge = floor.edges.find(function (item) {
                return String(item.id) === String(endpoint.edge);
            });
            const point = edge && edge.geometry ? edge.geometry[Number(endpoint.point_index)] : null;
            return point ? [point[0], point[1]] : null;
        }

        function setMode(nextMode) {
            mode = nextMode;
            selectedSnapEndpoints = [];
            rightDrawing = false;
            lastDragPoint = null;
            document.querySelectorAll("[data-indoor-mode]").forEach(function (button) {
                button.classList.toggle("is-active", button.getAttribute("data-indoor-mode") === mode);
            });
            document.querySelectorAll("[data-mode-panel]").forEach(function (panel) {
                panel.classList.toggle("is-hidden", panel.getAttribute("data-mode-panel") !== mode);
            });
            if (hintEl) {
                hintEl.textContent = modeHints[mode] || "";
            }
            render();
        }

        function updateCoreField() {
            if (!typeSelect || !coreField || !coreSelect) {
                return;
            }
            const nodeType = typeSelect.value;
            const isVerticalCore = nodeType === "elevator" || nodeType === "stairs";
            coreField.classList.toggle("is-hidden", !isVerticalCore);
            Array.from(coreSelect.options).forEach(function (option) {
                const optionType = option.getAttribute("data-core-type");
                option.hidden = Boolean(optionType && optionType !== nodeType);
            });
            if (!isVerticalCore) {
                coreSelect.value = "";
                return;
            }
            const selectedType = coreSelect.selectedOptions[0]
                ? coreSelect.selectedOptions[0].getAttribute("data-core-type")
                : "";
            if (!coreSelect.value || selectedType !== nodeType) {
                coreSelect.value = defaultCoreByType[nodeType] || "";
            }
        }

        function makeSvg(tag, attrs) {
            const node = document.createElementNS(NS, tag);
            Object.keys(attrs || {}).forEach(function (key) {
                node.setAttribute(key, attrs[key]);
            });
            return node;
        }

        function markerClass(node) {
            return `indoor-collector-node is-${node.type || "hall"}`;
        }

        function drawNode(node) {
            const group = makeSvg("g", {
                class: markerClass(node),
                "data-node-id": node.id,
                transform: `translate(${node.x}, ${node.y})`
            });
            group.appendChild(makeSvg("circle", { r: node.type === "room" ? 12 : 10 }));
            const label = makeSvg("text", {
                x: 0,
                y: -18,
                "text-anchor": "middle"
            });
            label.textContent = node.name || node.id;
            group.appendChild(label);
            svg.appendChild(group);
        }

        function drawEndpointSelection() {
            selectedSnapEndpoints.forEach(function (endpoint, index) {
                const point = endpointPoint(endpoint);
                if (!point) {
                    return;
                }
                const group = makeSvg("g", {
                    class: "indoor-snap-selected",
                    transform: `translate(${point[0]}, ${point[1]})`
                });
                group.appendChild(makeSvg("circle", { r: 18 }));
                const text = makeSvg("text", { y: 5, "text-anchor": "middle" });
                text.textContent = String(index + 1);
                group.appendChild(text);
                svg.appendChild(group);
            });
        }

        function drawEditRoad() {
            if (editPoints.length >= 2) {
                svg.appendChild(makeSvg("polyline", {
                    class: "indoor-edit-edge",
                    points: pointsAttr(editPoints)
                }));
            }
            editPoints.forEach(function (point, index) {
                const group = makeSvg("g", {
                    class: "indoor-edit-point",
                    transform: `translate(${point[0]}, ${point[1]})`
                });
                group.appendChild(makeSvg("circle", { r: 8 }));
                const text = makeSvg("text", { y: 4, "text-anchor": "middle" });
                text.textContent = String(index + 1);
                group.appendChild(text);
                svg.appendChild(group);
            });
        }

        function render() {
            const key = floorKey();
            const floor = floorPayload(key);
            const meta = data.meta || {};
            const width = Number(meta.width || 1672);
            const height = Number(meta.height || 941);
            const asset = (meta.floor_assets || {})[key] || (meta.floor_assets || {})[Number(key)];
            svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
            svg.innerHTML = "";
            if (floorTitle) {
                floorTitle.textContent = `${key}F`;
            }

            if (asset) {
                svg.appendChild(makeSvg("image", {
                    href: `/static/${asset}`,
                    x: 0,
                    y: 0,
                    width: width,
                    height: height,
                    preserveAspectRatio: "xMidYMid meet"
                }));
            }

            floor.edges.forEach(function (edge) {
                const geometry = edge.geometry || [];
                if (geometry.length < 2) {
                    return;
                }
                svg.appendChild(makeSvg("polyline", {
                    class: "indoor-collector-edge",
                    "data-edge-id": edge.id,
                    points: pointsAttr(geometry)
                }));
            });

            floor.links.forEach(function (link) {
                const geometry = link.geometry || [];
                if (geometry.length < 2) {
                    return;
                }
                svg.appendChild(makeSvg("polyline", {
                    class: "indoor-collector-link",
                    "data-link-id": link.id,
                    points: pointsAttr(geometry)
                }));
            });

            if (mode === "road" || mode === "snap") {
                floor.edges.forEach(function (edge) {
                    (edge.geometry || []).forEach(function (point, index) {
                        const group = makeSvg("g", {
                            class: "indoor-road-point",
                            "data-edge-id": edge.id,
                            "data-point-index": index,
                            transform: `translate(${point[0]}, ${point[1]})`
                        });
                        group.appendChild(makeSvg("circle", { r: mode === "snap" ? 8 : 5 }));
                        svg.appendChild(group);
                    });
                });
            }

            floor.nodes.forEach(drawNode);
            drawEndpointSelection();
            drawEditRoad();
            updateSummary();
            updateExport();
        }

        function addNode(event) {
            const point = svgPoint(event);
            if (!point) {
                return;
            }
            const key = floorKey();
            const floor = floorPayload(key);
            const nodeType = typeSelect ? typeSelect.value : "room";
            const name = nameInput && nameInput.value.trim()
                ? nameInput.value.trim()
                : `${key}F ${nodeType === "room" ? "房间门点" : "关键点"}${floor.nodes.length + 1}`;
            const coreId = coreSelect && (nodeType === "elevator" || nodeType === "stairs")
                ? coreSelect.value
                : "";
            pushUndo();
            requestJson(endpoints.node, {
                floor: Number(key),
                x: point[0],
                y: point[1],
                type: nodeType,
                name: name,
                core_id: coreId
            }).then(function (payload) {
                floor.nodes = floor.nodes.filter(function (item) { return item.id !== payload.node.id; });
                floor.nodes.push(payload.node);
                updateSummary(payload.summary);
                render();
                status(`已采集关键点：${payload.node.name}`);
            }).catch(function (error) {
                status(error.message);
            });
        }

        function addEditPoint(point) {
            if (!point) {
                return;
            }
            if (editPoints.length && pointDistance(editPoints[editPoints.length - 1], point) < 8) {
                return;
            }
            editPoints.push(point);
            render();
            status(`当前道路 ${editPoints.length} 个采样点。`);
        }

        function saveRoad() {
            if (editPoints.length < 2) {
                status("道路至少需要两个采样点。");
                return Promise.resolve();
            }
            const key = floorKey();
            const floor = floorPayload(key);
            const name = roadNameInput && roadNameInput.value.trim()
                ? roadNameInput.value.trim()
                : `${key}F 室内道路${floor.edges.length + 1}`;
            pushUndo();
            return requestJson(endpoints.edge, {
                floor: Number(key),
                name: name,
                road_type: roadTypeSelect ? roadTypeSelect.value : "corridor",
                geometry: editPoints
            }).then(function (payload) {
                floor.edges = floor.edges.filter(function (item) { return item.id !== payload.edge.id; });
                floor.edges.push(payload.edge);
                editPoints = [];
                rightDrawing = false;
                lastDragPoint = null;
                updateSummary(payload.summary);
                render();
                status(`已保存道路：${payload.edge.name}`);
            }).catch(function (error) {
                status(error.message);
            });
        }

        function selectSnapEndpoint(endpoint) {
            const key = endpointKey(endpoint);
            if (!key) {
                return;
            }
            const existingIndex = selectedSnapEndpoints.findIndex(function (item) {
                return endpointKey(item) === key;
            });
            if (existingIndex >= 0) {
                selectedSnapEndpoints.splice(existingIndex, 1);
                render();
                status("已取消该吸附端点。");
                return;
            }
            if (selectedSnapEndpoints.length >= 2) {
                selectedSnapEndpoints = [];
            }
            selectedSnapEndpoints.push(endpoint);
            render();
            if (selectedSnapEndpoints.length < 2) {
                status(`已选择端点：${endpointLabel(endpoint)}，请继续选择另一个端点。`);
                return;
            }
            pushUndo();
            requestJson(endpoints.link, {
                floor: Number(floorKey()),
                a: selectedSnapEndpoints[0],
                b: selectedSnapEndpoints[1]
            }).then(function (payload) {
                const floor = floorPayload(floorKey());
                floor.links = floor.links.filter(function (item) { return item.id !== payload.link.id; });
                floor.links.push(payload.link);
                selectedSnapEndpoints = [];
                updateSummary(payload.summary);
                render();
                status("已保存吸附关系。");
            }).catch(function (error) {
                status(error.message);
            });
        }

        function deleteNode(nodeId) {
            if (!window.confirm("删除这个关键点及相关吸附吗？")) {
                return;
            }
            pushUndo();
            deleteJson(`${endpoints.nodeBase}/${encodeURIComponent(nodeId)}`).then(function (payload) {
                const floor = floorPayload(floorKey());
                floor.nodes = floor.nodes.filter(function (node) { return String(node.id) !== String(nodeId); });
                floor.links = floor.links.filter(function (link) {
                    return String((link.a || {}).id) !== String(nodeId) && String((link.b || {}).id) !== String(nodeId);
                });
                updateSummary(payload.summary);
                render();
                status("已删除关键点。");
            }).catch(function (error) {
                status(error.message);
            });
        }

        function deleteEdge(edgeId) {
            if (!window.confirm("删除这条道路及相关吸附吗？")) {
                return;
            }
            pushUndo();
            deleteJson(`${endpoints.edgeBase}/${encodeURIComponent(edgeId)}`).then(function (payload) {
                const floor = floorPayload(floorKey());
                floor.edges = floor.edges.filter(function (edge) { return String(edge.id) !== String(edgeId); });
                floor.links = floor.links.filter(function (link) {
                    return String((link.a || {}).edge) !== String(edgeId) && String((link.b || {}).edge) !== String(edgeId);
                });
                updateSummary(payload.summary);
                render();
                status("已删除道路。");
            }).catch(function (error) {
                status(error.message);
            });
        }

        function deleteRoadPoint(edgeId, pointIndex) {
            if (!window.confirm("删除这个道路采样点吗？")) {
                return;
            }
            pushUndo();
            deleteJson(`${endpoints.edgeBase}/${encodeURIComponent(edgeId)}/point/${pointIndex}`).then(function (payload) {
                const floor = floorPayload(floorKey());
                const edge = floor.edges.find(function (item) {
                    return String(item.id) === String(edgeId);
                });
                if (edge && edge.geometry) {
                    edge.geometry.splice(Number(pointIndex), 1);
                }
                floor.links = floor.links.filter(function (link) {
                    const a = link.a || {};
                    const b = link.b || {};
                    return !(
                        (String(a.edge) === String(edgeId) && Number(a.point_index) === Number(pointIndex))
                        || (String(b.edge) === String(edgeId) && Number(b.point_index) === Number(pointIndex))
                    );
                });
                updateSummary(payload.summary);
                render();
                status("已删除道路点。");
            }).catch(function (error) {
                status(error.message);
            });
        }

        function deleteLink(linkId) {
            pushUndo();
            deleteJson(`${endpoints.linkBase}/${encodeURIComponent(linkId)}`).then(function (payload) {
                const floor = floorPayload(floorKey());
                floor.links = floor.links.filter(function (link) { return String(link.id) !== String(linkId); });
                updateSummary(payload.summary);
                render();
                status("已删除吸附关系。");
            }).catch(function (error) {
                status(error.message);
            });
        }

        svg.addEventListener("click", function (event) {
            const nodeMarker = event.target.closest("[data-node-id]");
            const roadPoint = event.target.closest("[data-point-index]");
            const linkLine = event.target.closest("[data-link-id]");
            if (linkLine && mode === "snap") {
                deleteLink(linkLine.getAttribute("data-link-id"));
                return;
            }
            if (mode === "snap") {
                if (nodeMarker) {
                    selectSnapEndpoint({ type: "node", id: nodeMarker.getAttribute("data-node-id") });
                    return;
                }
                if (roadPoint) {
                    selectSnapEndpoint({
                        type: "road",
                        edge: roadPoint.getAttribute("data-edge-id"),
                        point_index: Number(roadPoint.getAttribute("data-point-index"))
                    });
                    return;
                }
                status("吸附模式下请选择关键点或道路采样点。");
                return;
            }
            if (nodeMarker || roadPoint) {
                return;
            }
            if (mode === "road") {
                addEditPoint(svgPoint(event));
                return;
            }
            addNode(event);
        });

        svg.addEventListener("contextmenu", function (event) {
            event.preventDefault();
            const nodeMarker = event.target.closest("[data-node-id]");
            const roadPoint = event.target.closest("[data-point-index]");
            const edgeLine = event.target.closest("[data-edge-id]");
            const linkLine = event.target.closest("[data-link-id]");
            if (mode !== "road" || (!rightDrawing && editPoints.length === 0)) {
                if (nodeMarker) {
                    deleteNode(nodeMarker.getAttribute("data-node-id"));
                    return;
                }
                if (roadPoint) {
                    deleteRoadPoint(
                        roadPoint.getAttribute("data-edge-id"),
                        Number(roadPoint.getAttribute("data-point-index"))
                    );
                    return;
                }
                if (linkLine) {
                    deleteLink(linkLine.getAttribute("data-link-id"));
                    return;
                }
                if (edgeLine) {
                    deleteEdge(edgeLine.getAttribute("data-edge-id"));
                    return;
                }
            }
            if (mode !== "road") {
                return;
            }
            const point = svgPoint(event);
            if (!rightDrawing) {
                rightDrawing = true;
                lastDragPoint = point;
                addEditPoint(point);
                status("右键连续打点已开始，移动鼠标采样，再次右键保存。");
                return;
            }
            if (point) {
                addEditPoint(point);
            }
            saveRoad();
        });

        svg.addEventListener("mousemove", function (event) {
            if (!rightDrawing || mode !== "road") {
                return;
            }
            const point = svgPoint(event);
            if (!point || (lastDragPoint && pointDistance(lastDragPoint, point) < 18)) {
                return;
            }
            lastDragPoint = point;
            addEditPoint(point);
        });

        svg.addEventListener("dblclick", function (event) {
            if (mode !== "road") {
                return;
            }
            event.preventDefault();
            saveRoad();
        });

        floorSelect.addEventListener("change", function () {
            editPoints = [];
            rightDrawing = false;
            selectedSnapEndpoints = [];
            render();
        });

        if (typeSelect) {
            typeSelect.addEventListener("change", updateCoreField);
        }

        document.addEventListener("click", function (event) {
            const modeButton = event.target.closest("[data-indoor-mode]");
            if (modeButton) {
                setMode(modeButton.getAttribute("data-indoor-mode"));
                return;
            }
            const button = event.target.closest("[data-indoor-action]");
            if (!button) {
                return;
            }
            const action = button.getAttribute("data-indoor-action");
            if (action === "export") {
                updateExport();
                status("已刷新导出 JSON。");
            }
            if (action === "save-road") {
                saveRoad();
            }
            if (action === "clear-current") {
                editPoints = [];
                rightDrawing = false;
                lastDragPoint = null;
                render();
                status("已清空当前未保存道路。");
            }
            if (action === "undo") {
                if (!undoStack.length) {
                    status("暂无可撤销内容。");
                    return;
                }
                redoStack.push(clone(data));
                restoreSnapshot(undoStack.pop(), "已撤销上一步采集。");
            }
            if (action === "redo") {
                if (!redoStack.length) {
                    status("暂无可恢复内容。");
                    return;
                }
                undoStack.push(clone(data));
                restoreSnapshot(redoStack.pop(), "已恢复上一步采集。");
            }
            if (action === "clear") {
                if (!window.confirm("确认清空全部室内采集数据吗？")) {
                    return;
                }
                pushUndo();
                requestJson(endpoints.clear, {}).then(function (payload) {
                    Object.keys(data.floors || {}).forEach(function (key) {
                        data.floors[key] = { nodes: [], edges: [], links: [] };
                    });
                    editPoints = [];
                    selectedSnapEndpoints = [];
                    updateSummary(payload.summary);
                    render();
                    status("已清空采集数据。");
                }).catch(function (error) {
                    status(error.message);
                });
            }
        });

        setMode("node");
        updateCoreField();
        render();
    });
}());
