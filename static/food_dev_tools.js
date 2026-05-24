(function () {
    const body = document.body;
    if (!body || !body.classList.contains("food-product-page")) return;

    const placeId = body.dataset.placeId || "xmu_manual";
    const devStorageKey = "tourism_food_dev_mode";

    const modalTemplate = `
        <div class="food-crop-dialog" role="dialog" aria-modal="true" aria-labelledby="foodCropTitle">
            <div class="food-crop-head">
                <div>
                    <span class="eyebrow">LOCAL FILE</span>
                    <h2 id="foodCropTitle">选择本地文件并裁剪</h2>
                </div>
                <div class="food-crop-head-actions">
                    <button type="button" class="food-crop-file-btn" data-food-crop-file>选择文件</button>
                    <button type="button" class="food-crop-close" data-food-crop-close>关闭</button>
                </div>
            </div>
            <input type="file" accept="image/*" data-food-crop-input hidden>
            <div class="food-crop-stage" data-food-crop-stage tabindex="0">
                <img class="food-crop-image" data-food-crop-image alt="">
                <div class="food-crop-box" data-food-crop-box hidden>
                    <span class="food-crop-handle nw" data-handle="nw"></span>
                    <span class="food-crop-handle n" data-handle="n"></span>
                    <span class="food-crop-handle ne" data-handle="ne"></span>
                    <span class="food-crop-handle e" data-handle="e"></span>
                    <span class="food-crop-handle se" data-handle="se"></span>
                    <span class="food-crop-handle s" data-handle="s"></span>
                    <span class="food-crop-handle sw" data-handle="sw"></span>
                    <span class="food-crop-handle w" data-handle="w"></span>
                </div>
            </div>
            <div class="food-crop-controls">
                <label>
                    <span>缩放</span>
                    <input type="range" min="1" max="3" step="0.01" value="1" data-food-crop-zoom>
                </label>
                <div class="food-crop-file-name" data-food-crop-name>未选择文件</div>
                <button type="button" class="food-crop-save" data-food-crop-save>保存裁剪结果</button>
            </div>
            <p class="food-crop-hint">拖动裁剪框或边角即可自由调整矩形区域，缩放只改变预览比例，不限制长宽比。</p>
        </div>
    `;

    const state = {
        enabled: localStorage.getItem(devStorageKey) === "1",
        foodKey: "",
        imageKind: "cover",
        dishIndex: null,
        targetImg: null,
        detailForm: null,
        modal: null,
        stage: null,
        imageEl: null,
        boxEl: null,
        fileInput: null,
        zoomInput: null,
        fileNameEl: null,
        statusEl: null,
        image: null,
        objectUrl: "",
        zoom: 1,
        fileName: "",
        imageBox: null,
        crop: null,
        aspectRatio: 0,
        dragMode: null,
        dragStart: null,
        dragCrop: null,
        pointerId: null,
    };

    function qsa(selector, root = document) {
        return Array.from(root.querySelectorAll(selector));
    }

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function staticUrl(path) {
        if (!path) return "";
        return path.startsWith("/static/") ? path : `/static/${path.replace(/^\/+/, "")}`;
    }

    function setStatus(message, isError = false) {
        if (!state.statusEl) return;
        state.statusEl.textContent = message || "";
        state.statusEl.classList.toggle("is-error", Boolean(isError));
    }

    function resetPreview() {
        if (state.objectUrl) {
            URL.revokeObjectURL(state.objectUrl);
        }
        state.objectUrl = "";
        state.image = null;
        state.fileName = "";
        state.imageBox = null;
        state.crop = null;
        state.dragMode = null;
        state.dragStart = null;
        state.dragCrop = null;
        state.pointerId = null;
        if (state.imageEl) {
            state.imageEl.removeAttribute("src");
            state.imageEl.hidden = true;
        }
        if (state.boxEl) {
            state.boxEl.hidden = true;
        }
        if (state.fileNameEl) {
            state.fileNameEl.textContent = "未选择文件";
        }
        if (state.zoomInput) {
            state.zoomInput.value = "1";
        }
        state.zoom = 1;
    }

    function ensureModal() {
        if (state.modal) return;
        state.modal = document.createElement("div");
        state.modal.className = "food-crop-modal";
        state.modal.hidden = true;
        state.modal.innerHTML = modalTemplate;
        document.body.appendChild(state.modal);

        state.stage = state.modal.querySelector("[data-food-crop-stage]");
        state.imageEl = state.modal.querySelector("[data-food-crop-image]");
        state.boxEl = state.modal.querySelector("[data-food-crop-box]");
        state.fileInput = state.modal.querySelector("[data-food-crop-input]");
        state.zoomInput = state.modal.querySelector("[data-food-crop-zoom]");
        state.fileNameEl = state.modal.querySelector("[data-food-crop-name]");
        state.statusEl = document.querySelector("[data-food-dev-status]");

        state.modal.querySelector("[data-food-crop-file]").addEventListener("click", () => {
            state.fileInput.click();
        });
        state.modal.querySelector("[data-food-crop-close]").addEventListener("click", closeCrop);
        state.modal.addEventListener("click", (event) => {
            if (event.target === state.modal) closeCrop();
        });
        state.modal.addEventListener("keydown", (event) => {
            if (event.key === "Escape") closeCrop();
        });
        state.fileInput.addEventListener("change", () => {
            const file = state.fileInput.files && state.fileInput.files[0];
            if (file) loadLocalFile(file);
        });
        state.zoomInput.addEventListener("input", () => {
            state.zoom = Number(state.zoomInput.value) || 1;
            renderCrop();
        });
        state.modal.querySelector("[data-food-crop-save]").addEventListener("click", saveCrop);
        state.stage.addEventListener("pointerdown", onStagePointerDown);
        state.stage.addEventListener("pointermove", onStagePointerMove);
        state.stage.addEventListener("pointerup", onStagePointerUp);
        state.stage.addEventListener("pointerleave", onStagePointerUp);
        state.stage.addEventListener("wheel", onStageWheel, { passive: false });
    }

    function setDevEnabled(enabled) {
        state.enabled = Boolean(enabled);
        body.classList.toggle("food-dev-enabled", state.enabled);
        localStorage.setItem(devStorageKey, state.enabled ? "1" : "0");
        qsa("[data-food-dev-toggle]").forEach((button) => {
            button.textContent = state.enabled ? "退出开发者模式" : "开发者模式";
            button.setAttribute("aria-pressed", state.enabled ? "true" : "false");
        });
        qsa("[data-food-dev-panel]").forEach((panel) => {
            panel.hidden = !state.enabled;
        });
    }

    function buildFormData(extra = {}) {
        const formData = new FormData();
        formData.append("place_id", placeId);
        Object.entries(extra).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== "") {
                formData.append(key, value);
            }
        });
        return formData;
    }

    async function apiUpdate(foodKey, formData) {
        const response = await fetch(`/api/food-media/${encodeURIComponent(foodKey)}/update`, {
            method: "POST",
            body: formData,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.error) {
            throw new Error(data.error || "保存失败");
        }
        return data;
    }

    function openCrop(options) {
        ensureModal();
        state.foodKey = options.foodKey || body.dataset.foodKey || "";
        state.imageKind = options.imageKind || "cover";
        state.dishIndex = Number.isFinite(options.dishIndex) ? options.dishIndex : null;
        state.targetImg = options.targetElement || null;
        state.detailForm = qsa("[data-food-dev-form]")[0] || null;
        state.aspectRatio = 0;
        if (state.imageKind === "cover" && state.targetImg) {
            const rect = state.targetImg.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                state.aspectRatio = rect.width / rect.height;
            }
        }
        resetPreview();
        state.modal.hidden = false;
        setStatus("请选择本地图片文件后再裁剪。");
        state.fileInput.value = "";
        window.setTimeout(() => state.fileInput.click(), 0);
    }

    function closeCrop() {
        if (!state.modal) return;
        state.modal.hidden = true;
        resetPreview();
        setStatus("");
    }

    function loadLocalFile(file) {
        if (!file || !file.type || !file.type.startsWith("image/")) {
            setStatus("请选择图片文件。", true);
            return;
        }
        resetPreview();
        state.fileName = file.name || "本地图片";
        state.fileNameEl.textContent = state.fileName;
        const objectUrl = URL.createObjectURL(file);
        state.objectUrl = objectUrl;
        const image = new Image();
        image.onload = () => {
            state.image = image;
            state.imageEl.src = objectUrl;
            state.imageEl.alt = state.fileName;
            state.imageEl.hidden = false;
            state.boxEl.hidden = false;
            state.zoom = 1;
            state.zoomInput.value = "1";
            renderCrop(true);
            setStatus("图片已载入，可拖动裁剪框或边角调整区域。");
        };
        image.onerror = () => {
            setStatus("图片读取失败，请重新选择文件。", true);
            resetPreview();
        };
        image.src = objectUrl;
    }

    function getStageMetrics() {
        const rect = state.stage.getBoundingClientRect();
        const image = state.image;
        const fit = Math.min(rect.width / image.naturalWidth, rect.height / image.naturalHeight);
        const scale = fit * state.zoom;
        const imageW = image.naturalWidth * scale;
        const imageH = image.naturalHeight * scale;
        const imageX = (rect.width - imageW) / 2;
        const imageY = (rect.height - imageH) / 2;
        return {
            stageWidth: rect.width,
            stageHeight: rect.height,
            imageX,
            imageY,
            imageW,
            imageH,
            scale,
        };
    }

    function clampCropRect(crop, metrics, ratio = 0) {
        const minSize = 40;
        const left = metrics.imageX;
        const top = metrics.imageY;
        const right = metrics.imageX + metrics.imageW;
        const bottom = metrics.imageY + metrics.imageH;
        if (ratio > 0) {
            let width = Math.max(minSize, Math.min(crop.w, metrics.imageW));
            let height = width / ratio;
            if (height > metrics.imageH) {
                height = Math.max(minSize, Math.min(crop.h || metrics.imageH, metrics.imageH));
                width = height * ratio;
            }
            if (width > metrics.imageW) {
                width = Math.max(minSize, Math.min(crop.w || metrics.imageW, metrics.imageW));
                height = width / ratio;
            }
            crop.w = Math.max(minSize, Math.min(width, metrics.imageW));
            crop.h = Math.max(minSize, Math.min(height, metrics.imageH));
        } else {
            crop.w = Math.max(minSize, Math.min(crop.w, metrics.imageW));
            crop.h = Math.max(minSize, Math.min(crop.h, metrics.imageH));
        }
        crop.x = clamp(crop.x, left, right - crop.w);
        crop.y = clamp(crop.y, top, bottom - crop.h);
        return crop;
    }

    function ensureCropRect() {
        if (!state.image || !state.imageBox) return;
        if (!state.crop) {
            const ratio = state.aspectRatio > 0 ? state.aspectRatio : 0;
            const maxW = state.imageBox.imageW * 0.84;
            const maxH = state.imageBox.imageH * 0.84;
            let w = maxW;
            let h = maxH;
            if (ratio > 0) {
                h = w / ratio;
                if (h > maxH) {
                    h = maxH;
                    w = h * ratio;
                }
            }
            state.crop = {
                x: state.imageBox.imageX + (state.imageBox.imageW - w) / 2,
                y: state.imageBox.imageY + (state.imageBox.imageH - h) / 2,
                w,
                h,
            };
        }
        state.crop = clampCropRect(state.crop, state.imageBox, state.aspectRatio);
    }

    function renderCrop(initial = false) {
        if (!state.image) return;
        state.imageBox = getStageMetrics();
        state.imageEl.style.left = `${state.imageBox.imageX}px`;
        state.imageEl.style.top = `${state.imageBox.imageY}px`;
        state.imageEl.style.width = `${state.imageBox.imageW}px`;
        state.imageEl.style.height = `${state.imageBox.imageH}px`;
        if (initial) {
            state.crop = null;
        }
        ensureCropRect();
        if (!state.crop) return;
        state.boxEl.hidden = false;
        state.boxEl.style.left = `${state.crop.x}px`;
        state.boxEl.style.top = `${state.crop.y}px`;
        state.boxEl.style.width = `${state.crop.w}px`;
        state.boxEl.style.height = `${state.crop.h}px`;
    }

    function pointInStage(event) {
        const rect = state.stage.getBoundingClientRect();
        return {
            x: event.clientX - rect.left,
            y: event.clientY - rect.top,
        };
    }

    function onStagePointerDown(event) {
        if (!state.image || !state.crop) return;
        const target = event.target.closest(".food-crop-handle, .food-crop-box");
        if (!target) return;
        event.preventDefault();
        state.dragStart = pointInStage(event);
        state.dragCrop = { ...state.crop };
        state.dragMode = target.classList.contains("food-crop-box") ? "move" : target.dataset.handle;
        state.pointerId = event.pointerId;
        state.stage.setPointerCapture(event.pointerId);
    }

    function resizeFromHandle(handle, dx, dy) {
        if (state.aspectRatio > 0) {
            const ratio = state.aspectRatio;
            const minSize = 40;
            const horizontalDelta = handle.includes("w") ? -dx : dx;
            const verticalDelta = handle.includes("n") ? -dy * ratio : dy * ratio;
            const delta = handle.includes("e") || handle.includes("w")
                ? horizontalDelta
                : verticalDelta;
            const nextW = clamp(state.dragCrop.w + delta, minSize, state.imageBox.imageW);
            let nextH = nextW / ratio;
            let finalW = nextW;
            let finalH = nextH;
            if (nextH > state.imageBox.imageH) {
                finalH = state.imageBox.imageH;
                finalW = finalH * ratio;
            }
            const centerX = state.dragCrop.x + state.dragCrop.w / 2;
            const centerY = state.dragCrop.y + state.dragCrop.h / 2;
            return clampCropRect({
                x: centerX - finalW / 2,
                y: centerY - finalH / 2,
                w: finalW,
                h: finalH,
            }, state.imageBox, ratio);
        }
        const next = { ...state.dragCrop };
        const minSize = 40;
        if (handle.includes("w")) {
            next.x = state.dragCrop.x + dx;
            next.w = state.dragCrop.w - dx;
        }
        if (handle.includes("e")) {
            next.w = state.dragCrop.w + dx;
        }
        if (handle.includes("n")) {
            next.y = state.dragCrop.y + dy;
            next.h = state.dragCrop.h - dy;
        }
        if (handle.includes("s")) {
            next.h = state.dragCrop.h + dy;
        }
        if (next.w < minSize) {
            if (handle.includes("w")) {
                next.x -= minSize - next.w;
            }
            next.w = minSize;
        }
        if (next.h < minSize) {
            if (handle.includes("n")) {
                next.y -= minSize - next.h;
            }
            next.h = minSize;
        }
        return clampCropRect(next, state.imageBox);
    }

    function onStagePointerMove(event) {
        if (!state.dragMode || !state.dragStart || !state.dragCrop) return;
        const pos = pointInStage(event);
        const dx = pos.x - state.dragStart.x;
        const dy = pos.y - state.dragStart.y;
        let next;
        if (state.dragMode === "move") {
            next = {
                x: state.dragCrop.x + dx,
                y: state.dragCrop.y + dy,
                w: state.dragCrop.w,
                h: state.dragCrop.h,
            };
            next = clampCropRect(next, state.imageBox, state.aspectRatio);
        } else {
            next = resizeFromHandle(state.dragMode, dx, dy);
        }
        state.crop = next;
        renderCrop();
    }

    function onStagePointerUp() {
        if (state.pointerId !== null && state.stage && state.stage.hasPointerCapture(state.pointerId)) {
            state.stage.releasePointerCapture(state.pointerId);
        }
        state.dragMode = null;
        state.dragStart = null;
        state.dragCrop = null;
        state.pointerId = null;
    }

    function onStageWheel(event) {
        if (!state.image) return;
        event.preventDefault();
        const delta = event.deltaY > 0 ? -0.06 : 0.06;
        const nextZoom = clamp(state.zoom + delta, 1, 3);
        state.zoom = nextZoom;
        state.zoomInput.value = String(nextZoom);
        renderCrop();
    }

    function cropToBlob() {
        return new Promise((resolve, reject) => {
            if (!state.image || !state.crop || !state.imageBox) {
                reject(new Error("请先选择图片并完成裁剪。"));
                return;
            }
            const canvas = document.createElement("canvas");
            const sx = ((state.crop.x - state.imageBox.imageX) / state.imageBox.imageW) * state.image.naturalWidth;
            const sy = ((state.crop.y - state.imageBox.imageY) / state.imageBox.imageH) * state.image.naturalHeight;
            const sw = (state.crop.w / state.imageBox.imageW) * state.image.naturalWidth;
            const sh = (state.crop.h / state.imageBox.imageH) * state.image.naturalHeight;
            canvas.width = Math.max(1, Math.round(sw));
            canvas.height = Math.max(1, Math.round(sh));
            const ctx = canvas.getContext("2d");
            ctx.drawImage(state.image, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
            canvas.toBlob((blob) => {
                if (!blob) {
                    reject(new Error("裁剪结果生成失败"));
                    return;
                }
                resolve(blob);
            }, "image/jpeg", 0.92);
        });
    }

    function getDetailScalarValues() {
        if (!state.detailForm) return {};
        return {
            rating: state.detailForm.elements.rating?.value,
            popularity: state.detailForm.elements.popularity?.value,
            avg_cost: state.detailForm.elements.avg_cost?.value,
            display_description: state.detailForm.elements.display_description?.value,
            recommendation_note: state.detailForm.elements.recommendation_note?.value,
            recommend_score_override: state.detailForm.elements.recommend_score_override?.value,
        };
    }

    function imageRoleSelector(role, dishIndex = null) {
        let selector = `[data-food-image-role="${role}"]`;
        if (dishIndex !== null && dishIndex !== undefined) {
            selector += `[data-dish-index="${dishIndex}"]`;
        }
        return selector;
    }

    function updateCurrentPageImages(foodKey, imageKind, savedPath, dishIndex = null) {
        const role = imageKind === "detail" ? "detail" : imageKind === "cover" ? "cover" : "dish";
        const src = `${staticUrl(savedPath)}?v=${Date.now()}`;
        qsa(imageRoleSelector(role, role === "dish" ? dishIndex : null)).forEach((img) => {
            if (img.dataset.foodKey !== foodKey) return;
            img.src = src;
        });
    }

    function updateCurrentPageText(record) {
        const description = record.display_description ?? "";
        qsa("[data-food-display-description]").forEach((node) => {
            node.textContent = description;
        });

        const mapping = [
            ["rating", record.rating],
            ["popularity", record.popularity],
            ["avg_cost", record.avg_cost !== undefined ? `￥${record.avg_cost}` : undefined],
        ];
        mapping.forEach(([key, value]) => {
            if (value === undefined || value === null || value === "") return;
            qsa(`[data-food-metric="${key}"]`).forEach((node) => {
                node.textContent = String(value);
            });
        });

        if (record.recommend_score_override !== undefined && record.recommend_score_override !== null && record.recommend_score_override !== "") {
            qsa('[data-food-metric="recommend_score"]').forEach((node) => {
                node.textContent = String(record.recommend_score_override);
            });
        }

        if (record.recommendation_note) {
            qsa("[data-food-recommendation-note]").forEach((node) => {
                node.textContent = record.recommendation_note;
            });
        }
    }

    async function saveCrop() {
        try {
            if (!state.image) {
                throw new Error("请先选择本地图片文件。");
            }
            const blob = await cropToBlob();
            const formData = buildFormData(getDetailScalarValues());
            const uploadField = state.imageKind === "cover" ? "cover_file" : state.imageKind === "detail" ? "detail_file" : "dish_file";
            formData.append(uploadField, blob, `${state.foodKey || "food"}-${state.imageKind}.jpg`);
            if (state.imageKind === "dish" && Number.isFinite(state.dishIndex)) {
                formData.append("dish_index", String(state.dishIndex));
            }
            setStatus("正在保存图片...");
            const data = await apiUpdate(state.foodKey, formData);
            const record = data.record || {};
            const savedPath =
                state.imageKind === "cover"
                    ? record.cover_image
                    : state.imageKind === "detail"
                        ? record.detail_image
                        : record.signature_dishes?.[state.dishIndex]?.image;
            if (savedPath) {
                updateCurrentPageImages(state.foodKey, state.imageKind, savedPath, state.dishIndex);
            }
            updateCurrentPageText(record);
            setStatus("已保存。");
            closeCrop();
        } catch (error) {
            setStatus(error.message, true);
        }
    }

    function bindDevToggle() {
        qsa("[data-food-dev-toggle]").forEach((button) => {
            button.addEventListener("click", () => setDevEnabled(!state.enabled));
        });
    }

    function bindImageTargets() {
        document.addEventListener("contextmenu", (event) => {
            if (!state.enabled) return;

            const detailTarget = event.target.closest("[data-food-detail-edit]");
            if (detailTarget) {
                event.preventDefault();
                openCrop({
                    foodKey: detailTarget.dataset.foodKey || body.dataset.foodKey,
                    imageKind: "detail",
                    targetElement: detailTarget.querySelector("img") || detailTarget,
                });
                return;
            }

            const coverTarget = event.target.closest("[data-food-cover-edit]");
            if (coverTarget) {
                event.preventDefault();
                openCrop({
                    foodKey: coverTarget.dataset.foodKey || body.dataset.foodKey,
                    imageKind: "cover",
                    targetElement: coverTarget.querySelector("img") || coverTarget,
                });
            }
        });

        const coverButton = document.querySelector("[data-food-dev-cover]");
        if (coverButton) {
            coverButton.addEventListener("click", () => {
                const cover = document.querySelector('[data-food-image-role="cover"][data-food-key="' + body.dataset.foodKey + '"]');
                openCrop({
                    foodKey: body.dataset.foodKey,
                    imageKind: "cover",
                    targetElement: cover || null,
                });
            });
        }

        const detailButton = document.querySelector("[data-food-dev-detail]");
        if (detailButton) {
            detailButton.addEventListener("click", () => {
                const hero = document.querySelector('[data-food-image-role="detail"][data-food-key="' + body.dataset.foodKey + '"]');
                openCrop({
                    foodKey: body.dataset.foodKey,
                    imageKind: "detail",
                    targetElement: hero || null,
                });
            });
        }

        qsa("[data-food-dev-dish-image]").forEach((button) => {
            button.addEventListener("click", () => {
                const index = Number(button.dataset.foodDevDishImage);
                const dishImage = document.querySelector(
                    '[data-food-image-role="dish"][data-food-key="' + body.dataset.foodKey + '"][data-dish-index="' + index + '"]'
                );
                openCrop({
                    foodKey: body.dataset.foodKey,
                    imageKind: "dish",
                    dishIndex: index,
                    targetElement: dishImage || null,
                });
            });
        });
    }

    function bindDetailForm() {
        const form = document.querySelector("[data-food-dev-form]");
        if (!form) return;
        state.detailForm = form;
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            try {
                setStatus("正在保存展示数据...");
                const formData = buildFormData({
                    rating: form.elements.rating?.value,
                    popularity: form.elements.popularity?.value,
                    avg_cost: form.elements.avg_cost?.value,
                    display_description: form.elements.display_description?.value,
                    recommendation_note: form.elements.recommendation_note?.value,
                    recommend_score_override: form.elements.recommend_score_override?.value,
                });
                [0, 1, 2].forEach((index) => {
                    const nameControl = form.elements[`dish_name_${index}`];
                    const priceControl = form.elements[`dish_price_${index}`];
                    if (nameControl) {
                        formData.append(`dish_name_${index}`, nameControl.value);
                    }
                    if (priceControl) {
                        formData.append(`dish_price_${index}`, priceControl.value);
                    }
                });
                const data = await apiUpdate(body.dataset.foodKey, formData);
                updateCurrentPageText(data.record || {});
                setStatus("已保存。");
                window.location.reload();
            } catch (error) {
                setStatus(error.message, true);
            }
        });
    }

    bindDevToggle();
    bindImageTargets();
    bindDetailForm();
    setDevEnabled(state.enabled);
})();
