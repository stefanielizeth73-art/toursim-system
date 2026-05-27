(function () {
    function formatFileSize(bytes) {
        if (!bytes) {
            return "0 KB";
        }
        if (bytes < 1024 * 1024) {
            return Math.max(1, Math.round(bytes / 1024)) + " KB";
        }
        return (bytes / 1024 / 1024).toFixed(1) + " MB";
    }

    function syncInputFiles(input, files) {
        if (typeof DataTransfer === "undefined") {
            return;
        }
        const transfer = new DataTransfer();
        files.forEach(function (file) {
            transfer.items.add(file);
        });
        input.files = transfer.files;
    }

    function createPreview(file, index, onRemove) {
        const item = document.createElement("article");
        item.className = "diary-dev-upload-preview";

        const media = document.createElement("div");
        media.className = "diary-dev-upload-preview__media";
        const objectUrl = URL.createObjectURL(file);

        if (file.type.indexOf("image/") === 0) {
            const image = document.createElement("img");
            image.src = objectUrl;
            image.alt = file.name;
            image.onload = function () {
                URL.revokeObjectURL(objectUrl);
            };
            media.appendChild(image);
        } else if (file.type.indexOf("video/") === 0) {
            const video = document.createElement("video");
            video.src = objectUrl;
            video.controls = true;
            video.playsInline = true;
            video.preload = "metadata";
            video.onloadedmetadata = function () {
                URL.revokeObjectURL(objectUrl);
            };
            media.appendChild(video);
        } else {
            const fallback = document.createElement("span");
            fallback.textContent = "文件";
            media.appendChild(fallback);
        }

        const copy = document.createElement("div");
        copy.className = "diary-dev-upload-preview__copy";

        const name = document.createElement("strong");
        name.textContent = file.name;
        const meta = document.createElement("span");
        meta.textContent = formatFileSize(file.size);
        copy.append(name, meta);

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "diary-dev-upload-preview__remove";
        remove.textContent = "移除";
        remove.addEventListener("click", function () {
            onRemove(index);
        });

        item.append(media, copy, remove);
        return item;
    }

    document.addEventListener("DOMContentLoaded", function () {
        const manager = document.querySelector("[data-dev-media-manager]");
        if (!manager) {
            return;
        }

        const checkboxes = Array.from(manager.querySelectorAll("[data-dev-media-checkbox]"));
        const removeCount = manager.querySelector("[data-dev-remove-count]");
        const selectAll = manager.querySelector("[data-dev-select-all]");
        const clearSelection = manager.querySelector("[data-dev-clear-selection]");
        const fileInput = manager.querySelector("[data-dev-file-input]");
        const fileTrigger = manager.querySelector("[data-dev-file-trigger]");
        const fileSummary = manager.querySelector("[data-dev-file-summary]");
        const previewList = manager.querySelector("[data-dev-file-preview-list]");
        const dropZone = manager.querySelector("[data-dev-drop-zone]");
        let pendingFiles = [];

        function updateExistingSelection() {
            const selected = checkboxes.filter(function (checkbox) {
                return checkbox.checked;
            });
            if (removeCount) {
                removeCount.textContent = String(selected.length);
            }
            checkboxes.forEach(function (checkbox) {
                const item = checkbox.closest("[data-dev-media-item]");
                const state = item ? item.querySelector("[data-dev-media-state]") : null;
                if (item) {
                    item.classList.toggle("is-selected-for-removal", checkbox.checked);
                }
                if (state) {
                    state.textContent = checkbox.checked ? "已选中，保存后删除" : "点击选中，保存后删除";
                }
            });
        }

        function renderPendingFiles() {
            if (!previewList || !fileInput) {
                return;
            }
            previewList.replaceChildren();
            pendingFiles.forEach(function (file, index) {
                previewList.appendChild(createPreview(file, index, function (removeIndex) {
                    pendingFiles.splice(removeIndex, 1);
                    syncInputFiles(fileInput, pendingFiles);
                    renderPendingFiles();
                }));
            });
            if (fileSummary) {
                const totalSize = pendingFiles.reduce(function (sum, file) {
                    return sum + file.size;
                }, 0);
                fileSummary.textContent = pendingFiles.length
                    ? pendingFiles.length + " 个待上传，合计 " + formatFileSize(totalSize)
                    : "还没有选择新文件";
            }
        }

        function appendFiles(fileList) {
            const incoming = Array.from(fileList || []).filter(function (file) {
                return file.type.indexOf("image/") === 0 || file.type.indexOf("video/") === 0;
            });
            pendingFiles = pendingFiles.concat(incoming);
            syncInputFiles(fileInput, pendingFiles);
            renderPendingFiles();
        }

        checkboxes.forEach(function (checkbox) {
            checkbox.addEventListener("change", updateExistingSelection);
        });
        if (selectAll) {
            selectAll.addEventListener("click", function () {
                checkboxes.forEach(function (checkbox) {
                    checkbox.checked = true;
                });
                updateExistingSelection();
            });
        }
        if (clearSelection) {
            clearSelection.addEventListener("click", function () {
                checkboxes.forEach(function (checkbox) {
                    checkbox.checked = false;
                });
                updateExistingSelection();
            });
        }
        if (fileTrigger && fileInput) {
            fileTrigger.addEventListener("click", function () {
                fileInput.click();
            });
        }
        if (fileInput) {
            fileInput.addEventListener("change", function () {
                appendFiles(fileInput.files);
            });
        }
        if (dropZone) {
            ["dragenter", "dragover"].forEach(function (eventName) {
                dropZone.addEventListener(eventName, function (event) {
                    event.preventDefault();
                    dropZone.classList.add("is-dragging");
                });
            });
            ["dragleave", "drop"].forEach(function (eventName) {
                dropZone.addEventListener(eventName, function () {
                    dropZone.classList.remove("is-dragging");
                });
            });
            dropZone.addEventListener("drop", function (event) {
                event.preventDefault();
                appendFiles(event.dataTransfer.files);
            });
        }

        updateExistingSelection();
        renderPendingFiles();
    });
}());
