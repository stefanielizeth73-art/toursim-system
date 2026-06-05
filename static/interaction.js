(function () {
    const body = document.body;

    if (!body) {
        return;
    }

    const isDiaryPage = body.classList.contains("diary-list-page") || body.classList.contains("diary-search-page") || body.classList.contains("diary-detail-page") || body.classList.contains("diary-hub-page") || body.classList.contains("route-map-page");
    const isFoodPage = body.classList.contains("food-product-page");
    const isIndoorPage = body.classList.contains("indoor-page");

    let masonryRafId = 0;

    function layoutMasonryFeeds() {
        const feeds = document.querySelectorAll(".js-masonry-feed");
        feeds.forEach(function (feed) {
            const items = feed.querySelectorAll(".diary-post");
            if (!items.length) {
                return;
            }
            const computedStyle = window.getComputedStyle(feed);
            const rowGap = parseFloat(computedStyle.rowGap || computedStyle.gap || "16") || 16;
            const rowHeight = parseFloat(computedStyle.gridAutoRows || "12") || 12;

            items.forEach(function (item) {
                item.style.gridRowEnd = "auto";
                const height = item.getBoundingClientRect().height;
                const span = Math.ceil((height + rowGap) / (rowHeight + rowGap));
                item.style.gridRowEnd = "span " + span;
            });
        });
    }

    function scheduleMasonryLayout() {
        if (masonryRafId) {
            return;
        }
        masonryRafId = window.requestAnimationFrame(function () {
            masonryRafId = 0;
            layoutMasonryFeeds();
        });
    }

    function initDiaryFeedMemory() {
        const feedRoot = document.querySelector("[data-diary-feed-page]");
        if (!feedRoot || !window.sessionStorage) {
            return;
        }

        const pageKey = location.pathname + location.search;
        const scrollKey = "diary-feed-scroll:" + pageKey;
        const restorePending = sessionStorage.getItem("diary-feed-restore");
        if (restorePending === pageKey) {
            const savedY = parseInt(sessionStorage.getItem(scrollKey) || "0", 10);
            if (!Number.isNaN(savedY)) {
                window.requestAnimationFrame(function () {
                    window.scrollTo(0, savedY);
                });
            }
            sessionStorage.removeItem("diary-feed-restore");
        }

        function saveFeedScroll() {
            sessionStorage.setItem(scrollKey, String(window.scrollY || window.pageYOffset || 0));
        }

        window.addEventListener("pagehide", saveFeedScroll);
        window.addEventListener("beforeunload", saveFeedScroll);

        document.querySelectorAll(".js-diary-entry").forEach(function (entry) {
            entry.addEventListener("click", function () {
                saveFeedScroll();
                sessionStorage.setItem("diary-feed-restore", pageKey);
            });
        });
    }

    function initDiaryBackLink() {
        const backLinks = document.querySelectorAll(".js-diary-back");
        if (!backLinks.length || !window.sessionStorage) {
            return;
        }

        backLinks.forEach(function (link) {
            link.addEventListener("click", function (event) {
                const referrer = document.referrer || "";
                const hasDiaryReferrer = referrer.indexOf(location.origin + "/diaries") === 0;
                if (hasDiaryReferrer && window.history.length > 1) {
                    event.preventDefault();
                    const referrerUrl = new URL(referrer);
                    sessionStorage.setItem("diary-feed-restore", referrerUrl.pathname + referrerUrl.search);
                    window.history.back();
                }
            });
        });
    }

    function scopedQuery(root, selector) {
        const scope = root || document;
        const nodes = [];
        if (scope.matches && scope.matches(selector)) {
            nodes.push(scope);
        }
        if (scope.querySelectorAll) {
            nodes.push.apply(nodes, Array.from(scope.querySelectorAll(selector)));
        }
        return nodes;
    }

    function initDeferredDiaryImages(scope) {
        const lazyImages = scopedQuery(scope || document, "img[data-diary-lazy-src]");
        const lazyVideos = scopedQuery(scope || document, "video[data-diary-lazy-video]");
        if (!lazyImages.length && !lazyVideos.length) {
            return;
        }

        function loadImage(image) {
            const source = image.getAttribute("data-diary-lazy-src");
            if (!source) {
                return;
            }
            image.src = source;
            image.removeAttribute("data-diary-lazy-src");
            if (image.decode) {
                image.decode().catch(function () { }).then(function () {
                    image.classList.add("is-loaded");
                    scheduleMasonryLayout();
                });
            } else {
                image.classList.add("is-loaded");
                scheduleMasonryLayout();
            }
        }

        function loadVideo(video) {
            const source = video.getAttribute("data-diary-lazy-video");
            if (!source) {
                return;
            }
            video.src = source;
            video.removeAttribute("data-diary-lazy-video");
            video.load();
            scheduleMasonryLayout();
        }

        if (!("IntersectionObserver" in window)) {
            lazyImages.forEach(loadImage);
            lazyVideos.forEach(loadVideo);
            return;
        }

        const observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) {
                    return;
                }
                if (entry.target.tagName === "VIDEO") {
                    loadVideo(entry.target);
                } else {
                    loadImage(entry.target);
                }
                observer.unobserve(entry.target);
            });
        }, {
            rootMargin: "220px 0px",
            threshold: 0.01
        });

        lazyImages.forEach(function (image) {
            observer.observe(image);
        });
        lazyVideos.forEach(function (video) {
            observer.observe(video);
        });
    }

    function initDiaryGallery() {
        const galleries = document.querySelectorAll("[data-gallery]");
        galleries.forEach(function (gallery) {
            const items = Array.from(gallery.querySelectorAll("[data-gallery-item]"));
            const dots = Array.from(gallery.querySelectorAll("[data-gallery-dot]"));
            const currentNode = gallery.querySelector("[data-gallery-current]");
            const prevButton = gallery.querySelector("[data-gallery-prev]");
            const nextButton = gallery.querySelector("[data-gallery-next]");
            const stage = gallery.querySelector(".diary-gallery-stage");
            if (!items.length) {
                return;
            }

            let activeIndex = Math.max(0, items.findIndex(function (item) {
                return item.classList.contains("is-active");
            }));
            if (activeIndex < 0) {
                activeIndex = 0;
            }

            function renderGallery() {
                items.forEach(function (item, index) {
                    item.classList.toggle("is-active", index === activeIndex);
                });
                if (stage) {
                    const activeItem = items[activeIndex];
                    const imageUrl = activeItem && activeItem.getAttribute("data-gallery-src");
                    const thumbUrl = activeItem && activeItem.getAttribute("data-gallery-thumb");
                    const blurBase64 = activeItem && activeItem.getAttribute("data-gallery-blur");

                    if (imageUrl) {
                        // 1. 瞬间先将背景设置为内联的 Base64 极微磨砂占位（物理 0ms 秒开呈现）
                        const currentThumb = blurBase64 || thumbUrl || imageUrl;
                        stage.style.backgroundImage = "url('" + currentThumb.replace(/'/g, "\\'") + "')";
                        stage.style.backgroundRepeat = "no-repeat";
                        stage.style.backgroundPosition = "center center";
                        stage.style.backgroundSize = "contain";

                        const loadingIndex = activeIndex;

                        // 2. 若存在缩略图且有内联占位，在后台并发加载缩略图进行半高清过渡
                        if (blurBase64 && thumbUrl) {
                            const thumbImg = new Image();
                            thumbImg.src = thumbUrl;
                            thumbImg.onload = function() {
                                if (activeIndex === loadingIndex) {
                                    stage.style.backgroundImage = "url('" + thumbUrl.replace(/'/g, "\\'") + "')";
                                }
                            };
                        }

                        // 3. 异步在后台下载大图，下载完成后平滑替换为高清大图，完全避免大图请求/解码阻塞粒子动画主线程
                        const img = new Image();
                        img.src = imageUrl;
                        img.onload = function() {
                            if (activeIndex === loadingIndex) {
                                stage.style.backgroundImage = "url('" + imageUrl.replace(/'/g, "\\'") + "')";
                            }
                        };
                    } else {
                        stage.style.backgroundImage = "none";
                    }
                }
                dots.forEach(function (dot, index) {
                    dot.classList.toggle("is-active", index === activeIndex);
                });
                if (currentNode) {
                    currentNode.textContent = String(activeIndex + 1);
                }
                if (prevButton) {
                    prevButton.disabled = activeIndex === 0;
                }
                if (nextButton) {
                    nextButton.disabled = activeIndex === items.length - 1;
                }

                // 4. 翻页预加载相邻的下一张和上一张图片，使用浏览器缓存，使其在翻页时高清原图也能秒开
                preloadAdjacentImages(activeIndex);
            }

            function preloadAdjacentImages(currentIndex) {
                [currentIndex - 1, currentIndex + 1].forEach(function(index) {
                    if (index >= 0 && index < items.length) {
                        const item = items[index];
                        const imageUrl = item && item.getAttribute("data-gallery-src");
                        if (imageUrl) {
                            const img = new Image();
                            img.src = imageUrl;
                        }
                    }
                });
            }

            function setActiveIndex(index) {
                if (index < 0 || index >= items.length || index === activeIndex) {
                    return;
                }
                activeIndex = index;
                renderGallery();
            }

            if (prevButton) {
                prevButton.addEventListener("click", function () {
                    setActiveIndex(activeIndex - 1);
                });
            }
            if (nextButton) {
                nextButton.addEventListener("click", function () {
                    setActiveIndex(activeIndex + 1);
                });
            }
            dots.forEach(function (dot) {
                dot.addEventListener("click", function () {
                    setActiveIndex(parseInt(dot.getAttribute("data-gallery-dot") || "0", 10));
                });
            });

            gallery.addEventListener("click", function (event) {
                if (
                    event.target.closest("[data-gallery-prev]") ||
                    event.target.closest("[data-gallery-next]") ||
                    event.target.closest("[data-gallery-dot]") ||
                    event.target.closest("video")
                ) {
                    return;
                }
                if (!stage) {
                    return;
                }
                const rect = stage.getBoundingClientRect();
                const clickX = event.clientX - rect.left;
                if (clickX < rect.width * 0.4) {
                    setActiveIndex(activeIndex - 1);
                } else if (clickX > rect.width * 0.6) {
                    setActiveIndex(activeIndex + 1);
                }
            });

            renderGallery();
        });
    }

    function initCommentDrafts() {
        const detailRoot = document.querySelector("[data-diary-detail-root]");
        const inlineForm = document.querySelector("[data-comment-draft-form]");
        const replySheet = document.querySelector("[data-comment-reply-sheet]");
        if (!detailRoot || !inlineForm || !window.sessionStorage) {
            return;
        }

        const diaryId = detailRoot.getAttribute("data-diary-id");
        const inlineDraftKey = "diary-comment-inline:" + diaryId;
        const replyDraftKey = "diary-comment-reply:" + diaryId;
        const posted = detailRoot.getAttribute("data-comment-posted") === "1";
        const inlineTextarea = inlineForm.querySelector("[data-comment-draft-input]");
        const inlineParentInput = inlineForm.querySelector('input[name="parent_id"]');
        const replyHint = document.getElementById("reply-hint");

        function setInlineMode(targetId, targetAuthor) {
            if (inlineParentInput) {
                inlineParentInput.value = targetId || "";
            }
            if (replyHint) {
                replyHint.textContent = targetId ? ("当前将回复 " + targetAuthor) : "当前发布为一级评论";
            }
        }

        function saveInlineDraft() {
            if (!inlineTextarea) {
                return;
            }
            sessionStorage.setItem(inlineDraftKey, JSON.stringify({
                content: inlineTextarea.value || "",
                parentId: inlineParentInput ? inlineParentInput.value : ""
            }));
        }

        if (posted) {
            sessionStorage.removeItem(inlineDraftKey);
            sessionStorage.removeItem(replyDraftKey);
            const url = new URL(window.location.href);
            url.searchParams.delete("comment_posted");
            window.history.replaceState({}, "", url.pathname + url.search + url.hash);
        } else {
            const inlineRaw = sessionStorage.getItem(inlineDraftKey);
            if (inlineRaw && inlineTextarea) {
                try {
                    const inlineDraft = JSON.parse(inlineRaw);
                    inlineTextarea.value = inlineDraft.content || "";
                    setInlineMode(inlineDraft.parentId || "", "");
                } catch (error) {
                    sessionStorage.removeItem(inlineDraftKey);
                }
            }
        }

        if (inlineTextarea) {
            inlineTextarea.addEventListener("input", saveInlineDraft);
        }
        if (inlineForm) {
            inlineForm.addEventListener("submit", function () {
                sessionStorage.removeItem(inlineDraftKey);
            });
        }

        if (replyHint) {
            replyHint.addEventListener("click", function () {
                setInlineMode("", "");
                saveInlineDraft();
                if (inlineTextarea) {
                    inlineTextarea.focus();
                }
            });
        }

        if (!replySheet) {
            return;
        }

        const replyParentInput = replySheet.querySelector('input[name="parent_id"]');
        const replyTextarea = replySheet.querySelector("[data-reply-draft-input]");
        const replyTarget = document.getElementById("reply-sheet-target");

        function persistReplyDraft() {
            if (!replyTextarea) {
                return;
            }
            sessionStorage.setItem(replyDraftKey, JSON.stringify({
                content: replyTextarea.value || "",
                parentId: replyParentInput ? replyParentInput.value : "",
                author: replySheet.dataset.replyAuthor || ""
            }));
        }

        function applyReplyDraft(payload) {
            if (!payload) {
                return;
            }
            if (replyParentInput) {
                replyParentInput.value = payload.parentId || "";
            }
            replySheet.dataset.replyAuthor = payload.author || "";
            if (replyTextarea) {
                replyTextarea.value = payload.content || "";
            }
            if (replyTarget) {
                replyTarget.textContent = payload.author ? ("回复给 " + payload.author) : "回复给某位同学";
            }
        }

        function openReplySheet(targetId, targetAuthor) {
            applyReplyDraft({
                content: replyTextarea ? replyTextarea.value : "",
                parentId: targetId,
                author: targetAuthor
            });
            replySheet.hidden = false;
            body.classList.add("reply-sheet-open");
            window.requestAnimationFrame(function () {
                replySheet.classList.add("is-open");
            });
            if (replyTextarea) {
                replyTextarea.focus();
            }
            persistReplyDraft();
        }

        function closeReplySheet() {
            replySheet.classList.remove("is-open");
            body.classList.remove("reply-sheet-open");
            window.setTimeout(function () {
                if (!replySheet.classList.contains("is-open")) {
                    replySheet.hidden = true;
                }
            }, 220);
        }

        const savedReply = sessionStorage.getItem(replyDraftKey);
        if (savedReply && !posted) {
            try {
                applyReplyDraft(JSON.parse(savedReply));
            } catch (error) {
                sessionStorage.removeItem(replyDraftKey);
            }
        }

        if (replyTextarea) {
            replyTextarea.addEventListener("input", persistReplyDraft);
        }
        replySheet.addEventListener("submit", function () {
            sessionStorage.removeItem(replyDraftKey);
        });
        replySheet.querySelectorAll("[data-reply-close]").forEach(function (node) {
            node.addEventListener("click", closeReplySheet);
        });

        document.querySelectorAll(".js-comment-reply-trigger").forEach(function (trigger) {
            trigger.addEventListener("click", function (event) {
                if (event.target && event.target.closest && event.target.closest("a")) {
                    return;
                }
                const replyId = trigger.getAttribute("data-reply-target") || "";
                const replyAuthor = trigger.getAttribute("data-reply-author") || "";
                openReplySheet(replyId, replyAuthor);
            });
            trigger.addEventListener("keydown", function (event) {
                if (event.key !== "Enter" && event.key !== " ") {
                    return;
                }
                if (event.target && event.target.closest && event.target.closest("a")) {
                    return;
                }
                event.preventDefault();
                const replyId = trigger.getAttribute("data-reply-target") || "";
                const replyAuthor = trigger.getAttribute("data-reply-author") || "";
                openReplySheet(replyId, replyAuthor);
            });
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && replySheet.classList.contains("is-open")) {
                closeReplySheet();
            }
        });
    }

    function initDiaryVideoGeneration() {
        const panel = document.querySelector("[data-diary-video-panel]");
        if (!panel) {
            return;
        }

        const button = panel.querySelector("[data-video-generate]");
        const promptInput = panel.querySelector("[data-video-prompt]");
        const statusNode = panel.querySelector("[data-video-status]");
        const preview = panel.querySelector("[data-video-preview]");
        const player = panel.querySelector("[data-video-player]");
        const downloadLink = panel.querySelector("[data-video-download]");
        const hasImage = panel.getAttribute("data-has-image") === "1";
        const apiReady = panel.getAttribute("data-api-ready") === "1";
        const startUrl = panel.getAttribute("data-start-url") || "";
        const templateUrl = panel.getAttribute("data-task-url-template") || "";
        let pollTimer = 0;
        let pollCount = 0;
        let hasGeneratedVideo = Boolean(player && player.getAttribute("src"));

        function setStatus(message, tone) {
            if (!statusNode) {
                return;
            }
            statusNode.textContent = message;
            statusNode.classList.toggle("is-error", tone === "error");
            statusNode.classList.toggle("is-success", tone === "success");
        }

        function setBusy(isBusy) {
            if (!button) {
                return;
            }
            button.disabled = isBusy || !hasImage;
            button.textContent = isBusy ? "生成中" : (hasImage ? (hasGeneratedVideo ? "重新生成" : "生成视频") : "需要图片");
        }

        function taskStatusUrl(taskId) {
            return templateUrl.replace(/\/0(?=($|[?#]))/, "/" + taskId);
        }

        function showVideo(url) {
            if (!url || !player || !preview) {
                return;
            }
            player.src = url;
            preview.hidden = false;
            if (downloadLink) {
                downloadLink.href = url + (url.indexOf("?") === -1 ? "?download=1" : "&download=1");
            }
            hasGeneratedVideo = true;
            setStatus("视频已生成并保存，可展开预览或下载。", "success");
        }

        function renderTask(task) {
            if (!task) {
                return;
            }
            if (task.local_video_url) {
                showVideo(task.local_video_url);
                setBusy(false);
                return;
            }
            if (task.status === "SUCCEEDED") {
                setStatus("视频已生成，正在保存到本地。");
                return;
            }
            if (task.status === "FAILED" || task.status === "CANCELED" || task.status === "UNKNOWN") {
                setStatus(task.error_message || "生成任务未完成，请稍后重试。", "error");
                setBusy(false);
                return;
            }
            setStatus(task.status === "RUNNING" ? "生成中，正在小步轮询进度。" : "任务已提交，正在排队。");
        }

        async function pollTask(taskId) {
            if (!taskId) {
                return;
            }
            window.clearTimeout(pollTimer);
            try {
                pollCount += 1;
                const response = await fetch(taskStatusUrl(taskId), { headers: { "Accept": "application/json" } });
                const payload = await response.json();
                if (!response.ok || !payload.ok) {
                    throw new Error(payload.error || "查询生成进度失败");
                }
                renderTask(payload.task);
                const status = payload.task && payload.task.status;
                if (status === "PENDING" || status === "RUNNING") {
                    if (statusNode) {
                        statusNode.textContent += " 第 " + pollCount + " 次检查。";
                    }
                    pollTimer = window.setTimeout(function () {
                        pollTask(taskId);
                    }, 5000);
                } else {
                    setBusy(false);
                }
            } catch (error) {
                setStatus(error.message || "查询生成进度失败", "error");
                setBusy(false);
            }
        }

        async function startGeneration() {
            if (!hasImage) {
                setStatus("这篇日记还没有图片，先补一张图再生成。", "error");
                return;
            }
            if (!apiReady) {
                setStatus("需要先配置 DASHSCOPE_API_KEY。", "error");
                return;
            }
            setBusy(true);
            pollCount = 0;
            setStatus("正在提交图文生视频任务。");
            try {
                const response = await fetch(startUrl, {
                    method: "POST",
                    headers: {
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        prompt: promptInput ? promptInput.value.trim() : ""
                    })
                });
                const payload = await response.json();
                if (!response.ok || !payload.ok) {
                    throw new Error(payload.error || "创建生成任务失败");
                }
                renderTask(payload.task);
                pollTask(payload.task.id);
            } catch (error) {
                setStatus(error.message || "创建生成任务失败", "error");
                setBusy(false);
            }
        }

        if (button) {
            button.addEventListener("click", startGeneration);
        }

        try {
            const rawTask = panel.getAttribute("data-initial-task");
            const initialTask = rawTask ? JSON.parse(rawTask) : null;
            renderTask(initialTask);
            if (apiReady && initialTask && (initialTask.status === "PENDING" || initialTask.status === "RUNNING")) {
                setBusy(true);
                pollTask(initialTask.id);
            }
        } catch (error) {
            return;
        }
    }

    document.querySelectorAll(".js-masonry-feed img, .js-masonry-feed video").forEach(function (media) {
        media.addEventListener("load", scheduleMasonryLayout, { once: true });
        media.addEventListener("loadedmetadata", scheduleMasonryLayout, { once: true });
    });

    function initDiaryInfiniteScroll() {
        const loader = document.getElementById("diaryInfiniteLoader");
        const feed = document.querySelector(".js-masonry-feed");
        if (!loader || !feed || loader.dataset.infiniteInit === "1") {
            return;
        }
        loader.dataset.infiniteInit = "1";
        body.classList.add("diary-infinite-ready");

        let nextUrl = loader.getAttribute("data-next-url") || "";
        let hasNext = loader.getAttribute("data-has-next") === "true" && Boolean(nextUrl);
        let loading = false;

        function setText(text) {
            const textNode = loader.querySelector(".diary-infinite-loader__text");
            if (textNode) {
                textNode.textContent = text;
            } else {
                loader.textContent = text;
            }
        }

        function buildAjaxUrl(urlValue) {
            const url = new URL(urlValue, window.location.origin);
            url.searchParams.set("ajax", "1");
            return url.toString();
        }

        function bindNewEntry(entry) {
            entry.addEventListener("click", function () {
                const feedRoot = document.querySelector("[data-diary-feed-page]");
                if (!feedRoot || !window.sessionStorage) {
                    return;
                }
                const pageKey = location.pathname + location.search;
                sessionStorage.setItem("diary-feed-scroll:" + pageKey, String(window.scrollY || window.pageYOffset || 0));
                sessionStorage.setItem("diary-feed-restore", pageKey);
            });
            scopedQuery(entry, "img, video").forEach(function (media) {
                media.addEventListener("load", scheduleMasonryLayout, { once: true });
                media.addEventListener("loadedmetadata", scheduleMasonryLayout, { once: true });
            });
            initDeferredDiaryImages(entry);
        }

        function showRetry() {
            loader.innerHTML = '<button type="button">加载失败，点击重试</button>';
            const button = loader.querySelector("button");
            if (button) {
                button.addEventListener("click", function () {
                    loader.innerHTML = '<span class="diary-infinite-loader__text">继续向下，加载更多日记</span>';
                    loadMore();
                }, { once: true });
            }
        }

        async function loadMore() {
            if (loading || !hasNext || !nextUrl) {
                return;
            }
            loading = true;
            setText("正在加载更多日记...");

            try {
                const response = await fetch(buildAjaxUrl(nextUrl), {
                    headers: { "Accept": "application/json" }
                });
                if (response.status === 401 || (response.redirected && response.url.indexOf("/login") !== -1)) {
                    window.location.assign(response.url || "/login");
                    return;
                }
                if (!response.ok) {
                    throw new Error("加载失败");
                }
                const contentType = response.headers.get("Content-Type") || "";
                if (contentType.indexOf("application/json") === -1) {
                    throw new Error("加载响应格式异常");
                }
                const payload = await response.json();
                if (!payload.ok) {
                    throw new Error(payload.error || "加载失败");
                }

                const fragment = document.createElement("template");
                fragment.innerHTML = (payload.html || "").trim();
                const newEntries = Array.from(fragment.content.querySelectorAll(".js-diary-entry"));
                feed.appendChild(fragment.content);
                newEntries.forEach(bindNewEntry);

                hasNext = Boolean(payload.has_next && payload.next_url);
                nextUrl = payload.next_url || "";
                loader.setAttribute("data-has-next", hasNext ? "true" : "false");
                loader.setAttribute("data-next-url", nextUrl);
                if (hasNext) {
                    setText("继续向下，加载更多日记");
                    if (observer) {
                        observer.observe(loader);
                    }
                } else {
                    setText("已加载全部日记");
                    if (observer) {
                        observer.disconnect();
                    }
                }
                scheduleMasonryLayout();
            } catch (error) {
                console.error(error);
                showRetry();
            } finally {
                loading = false;
            }
        }

        if (!hasNext) {
            setText("已加载全部日记");
            return;
        }
        let observer = null;
        if ("IntersectionObserver" in window) {
            observer = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        observer.unobserve(loader);
                        loadMore();
                    }
                });
            }, {
                rootMargin: "220px 0px",
                threshold: 0.01
            });
            observer.observe(loader);
        } else {
            loader.innerHTML = '<button type="button">加载更多日记</button>';
            const button = loader.querySelector("button");
            if (button) {
                button.addEventListener("click", loadMore);
            }
        }
    }

    function initIndoorRoutePicker() {
        if (!isIndoorPage || body.classList.contains("indoor-collector-page")) {
            return;
        }

        const form = document.getElementById("indoorRouteForm");
        if (!form) {
            return;
        }

        const startSelect = form.querySelector('select[name="start"]');
        const endSelect = form.querySelector('select[name="end"]');
        const searchInputs = Array.from(document.querySelectorAll("[data-indoor-node-search]"));
        const searchMenus = Array.from(document.querySelectorAll("[data-indoor-search-menu]"));
        const pickButtons = Array.from(document.querySelectorAll("[data-indoor-pick-mode]"));
        const pickTitle = document.querySelector("[data-indoor-pick-title]");
        const pickHint = document.querySelector("[data-indoor-pick-hint]");
        const submitButton = form.querySelector('button[type="submit"]');
        const clearButton = document.querySelector("[data-indoor-clear]");
        let pickMode = "start";

        const nodeOptions = Array.from((startSelect || endSelect || { options: [] }).options)
            .filter(function (option) {
                return option.value;
            })
            .map(function (option) {
                return {
                    id: option.value,
                    name: option.textContent.trim(),
                    floor: option.getAttribute("data-floor") || "",
                    type: option.getAttribute("data-type") || "other"
                };
            });

        function nodeById(nodeId) {
            return nodeOptions.find(function (node) {
                return node.id === nodeId;
            }) || null;
        }

        function setPickMode(mode) {
            pickMode = mode === "end" ? "end" : "start";
            body.setAttribute("data-indoor-pick-mode", pickMode);
            pickButtons.forEach(function (button) {
                button.classList.toggle("is-active", button.getAttribute("data-indoor-pick-mode") === pickMode);
            });
            if (pickTitle) {
                pickTitle.textContent = pickMode === "end" ? "正在设置终点" : "正在设置起点";
            }
            if (pickHint) {
                pickHint.textContent = pickMode === "end"
                    ? "点击地图上的采集点，直接设为目标位置。"
                    : "点击地图上的采集点，直接设为出发位置。";
            }
        }

        function selectForMode(mode) {
            return mode === "end" ? endSelect : startSelect;
        }

        function inputForMode(mode) {
            return document.querySelector(`[data-indoor-node-search="${mode}"]`);
        }

        function menuForMode(mode) {
            return document.querySelector(`[data-indoor-search-menu="${mode}"]`);
        }

        function setNodeValue(mode, nodeId) {
            const select = selectForMode(mode);
            const input = inputForMode(mode);
            const node = nodeById(nodeId);
            if (!select || !node) {
                return false;
            }
            select.value = node.id;
            if (input) {
                input.value = node.name;
            }
            return true;
        }

        function hideSearchMenus() {
            searchMenus.forEach(function (menu) {
                menu.classList.remove("is-open");
                menu.innerHTML = "";
            });
        }

        function filteredNodes(query) {
            const normalized = String(query || "").trim().toLowerCase();
            const source = normalized
                ? nodeOptions.filter(function (node) {
                    return node.name.toLowerCase().indexOf(normalized) !== -1 || node.id.toLowerCase().indexOf(normalized) !== -1;
                })
                : nodeOptions;
            return source.slice(0, 8);
        }

        function nodeTypeLabel(type) {
            switch (type) {
                case "elevator":
                    return "\u7535\u68af";
                case "stairs":
                    return "\u6b65\u68af";
                case "gate":
                    return "\u5165\u53e3";
                case "room":
                    return "\u623f\u95f4";
                default:
                    return "\u5176\u4ed6";
            }
        }

        function renderSearchMenu(mode, query) {
            const menu = menuForMode(mode);
            if (!menu) {
                return;
            }
            menu.innerHTML = "";
            filteredNodes(query).forEach(function (node) {
                const button = document.createElement("button");
                button.type = "button";
                button.setAttribute("role", "option");
                button.setAttribute("data-node-id", node.id);
                const name = document.createElement("strong");
                name.textContent = node.name;
                const meta = document.createElement("span");
                meta.textContent = `${node.floor}F \u00b7 ${nodeTypeLabel(node.type)}`;
                button.appendChild(name);
                button.appendChild(meta);
                button.addEventListener("mousedown", function (event) {
                    event.preventDefault();
                });
                button.addEventListener("click", function () {
                    setNodeValue(mode, node.id);
                    hideSearchMenus();
                });
                menu.appendChild(button);
            });
            if (!menu.children.length) {
                const empty = document.createElement("div");
                empty.className = "indoor-search-menu__empty";
                empty.textContent = "没有匹配的关键点";
                menu.appendChild(empty);
            }
            menu.classList.add("is-open");
        }

        function resolveInputToNode(mode) {
            const input = inputForMode(mode);
            const select = selectForMode(mode);
            if (!input || !select || select.value) {
                return;
            }
            const query = input.value.trim();
            if (!query) {
                return;
            }
            const exact = nodeOptions.find(function (node) {
                return node.name === query;
            });
            const fallback = exact || filteredNodes(query)[0];
            if (fallback) {
                setNodeValue(mode, fallback.id);
            }
        }

        function submitRoute() {
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit();
            } else {
                form.submit();
            }
        }

        pickButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                setPickMode(button.getAttribute("data-indoor-pick-mode"));
            });
        });

        searchInputs.forEach(function (input) {
            const mode = input.getAttribute("data-indoor-node-search") === "end" ? "end" : "start";
            input.addEventListener("focus", function () {
                renderSearchMenu(mode, input.value);
            });
            input.addEventListener("input", function () {
                const select = selectForMode(mode);
                if (select) {
                    select.value = "";
                }
                renderSearchMenu(mode, input.value);
            });
            input.addEventListener("keydown", function (event) {
                if (event.key === "Escape") {
                    hideSearchMenus();
                    input.blur();
                }
            });
        });

        document.addEventListener("click", function (event) {
            if (!event.target.closest(".indoor-search-field")) {
                hideSearchMenus();
            }
        });

        form.addEventListener("submit", function () {
            resolveInputToNode("start");
            resolveInputToNode("end");
            if (submitButton) {
                submitButton.classList.add("is-submitting");
                submitButton.textContent = "正在规划";
            }
        });

        if (clearButton) {
            clearButton.addEventListener("click", function (event) {
                if (typeof window.clearIndoorRouteSelection === "function") {
                    window.clearIndoorRouteSelection(event, clearButton);
                    return;
                }
                event.preventDefault();
                event.stopPropagation();

                const url = new URL("/indoor", window.location.origin);
                const params = url.searchParams;
                const buildingId = form.querySelector('input[name="building_id"]');
                const buildingName = form.querySelector('input[name="building_name"]');

                if (buildingId && buildingId.value) {
                    params.set("building_id", buildingId.value);
                }
                if (buildingName && buildingName.value) {
                    params.set("building_name", buildingName.value);
                }
                const verticalMode = form.querySelector('select[name="vertical_mode"]');
                if (verticalMode && verticalMode.value) {
                    params.set("vertical_mode", verticalMode.value);
                }
                params.set("clear", "1");

                if (startSelect) startSelect.value = "";
                if (endSelect) endSelect.value = "";
                searchInputs.forEach(function (input) {
                    input.value = "";
                });
                hideSearchMenus();
                window.location.assign(url.toString());
            });
        }

        document.querySelectorAll(".indoor-node-marker[data-node-id]").forEach(function (marker) {
            function chooseNode() {
                const nodeId = marker.getAttribute("data-node-id");
                if (!nodeId || !setNodeValue(pickMode, nodeId)) {
                    return;
                }
                submitRoute();
            }

            marker.addEventListener("click", chooseNode);
            marker.addEventListener("keydown", function (event) {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    chooseNode();
                }
            });
        });

        setPickMode(pickMode);
    }

    function initCompactDatalists() {
        const inputs = Array.from(document.querySelectorAll("input[list]"));
        if (!inputs.length) {
            return;
        }

        let activeInput = null;
        let activePanel = null;

        function getOptionValues(input) {
            const listId = input.getAttribute("data-native-list");
            const list = listId ? document.getElementById(listId) : null;
            if (!list) {
                return [];
            }
            return Array.from(list.options)
                .map(function (option) {
                    return (option.value || option.textContent || "").trim();
                })
                .filter(Boolean);
        }

        function placePanel(input, panel) {
            const rect = input.getBoundingClientRect();
            const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
            const width = Math.min(Math.max(rect.width, 220), Math.min(380, viewportWidth - 24));
            const left = Math.min(Math.max(rect.left, 12), viewportWidth - width - 12);
            panel.style.setProperty("--compact-datalist-width", width + "px");
            panel.style.left = left + "px";
            panel.style.top = (rect.bottom + 6) + "px";
        }

        function hidePanel() {
            if (activePanel) {
                activePanel.hidden = true;
            }
            activeInput = null;
            activePanel = null;
        }

        inputs.forEach(function (input) {
            const listId = input.getAttribute("list");
            if (!listId) {
                return;
            }

            input.setAttribute("data-native-list", listId);
            input.removeAttribute("list");
            input.setAttribute("autocomplete", "off");

            const panel = document.createElement("div");
            panel.className = "compact-datalist";
            if (document.body.classList.contains("places-darkroom-page") || document.body.classList.contains("place-dossier-page")) {
                panel.classList.add("places-compact-datalist");
            }
            panel.hidden = true;
            panel.setAttribute("role", "listbox");
            document.body.appendChild(panel);

            function chooseValue(value) {
                input.value = value;
                input.dispatchEvent(new Event("input", { bubbles: true }));
                input.dispatchEvent(new Event("change", { bubbles: true }));
                hidePanel();
                input.focus();
            }

            function renderOptions() {
                const query = input.value.trim().toLowerCase();
                const matches = getOptionValues(input).filter(function (value) {
                    return !query || value.toLowerCase().indexOf(query) !== -1;
                }).slice(0, 8);

                panel.innerHTML = "";
                if (!matches.length) {
                    panel.hidden = true;
                    return;
                }

                matches.forEach(function (value, index) {
                    const button = document.createElement("button");
                    button.type = "button";
                    button.setAttribute("role", "option");
                    button.textContent = value;
                    if (index === 0) {
                        button.classList.add("is-active");
                    }
                    button.addEventListener("click", function () {
                        chooseValue(value);
                    });
                    panel.appendChild(button);
                });

                activeInput = input;
                activePanel = panel;
                placePanel(input, panel);
                panel.hidden = false;
            }

            input.addEventListener("focus", renderOptions);
            input.addEventListener("input", renderOptions);
            input.addEventListener("click", renderOptions);
            input.addEventListener("keydown", function (event) {
                const firstOption = panel.querySelector("button");
                if (event.key === "Escape") {
                    hidePanel();
                } else if (event.key === "ArrowDown" && firstOption && !panel.hidden) {
                    event.preventDefault();
                    firstOption.focus();
                }
            });

            panel.addEventListener("keydown", function (event) {
                const buttons = Array.from(panel.querySelectorAll("button"));
                const currentIndex = buttons.indexOf(document.activeElement);
                if (event.key === "Escape") {
                    hidePanel();
                    input.focus();
                } else if (event.key === "ArrowDown") {
                    event.preventDefault();
                    buttons[Math.min(currentIndex + 1, buttons.length - 1)]?.focus();
                } else if (event.key === "ArrowUp") {
                    event.preventDefault();
                    if (currentIndex <= 0) {
                        input.focus();
                    } else {
                        buttons[currentIndex - 1]?.focus();
                    }
                }
            });

            panel.addEventListener("mousedown", function (event) {
                event.preventDefault();
            });
        });

        document.addEventListener("pointerdown", function (event) {
            if (!activeInput || !activePanel) {
                return;
            }
            if (event.target === activeInput || activePanel.contains(event.target)) {
                return;
            }
            hidePanel();
        });

        window.addEventListener("scroll", function () {
            if (activeInput && activePanel && !activePanel.hidden) {
                placePanel(activeInput, activePanel);
            }
        }, true);
        window.addEventListener("resize", hidePanel);
    }

    function initPlaceTagPopovers() {
        const root = document.querySelector("[data-place-tag-popovers]");
        if (!root) {
            return;
        }
        const triggers = Array.from(root.querySelectorAll("[data-place-tag-trigger]"));

        function closeAll(except) {
            triggers.forEach(function (trigger) {
                if (trigger === except) {
                    return;
                }
                const panel = document.getElementById(trigger.getAttribute("aria-controls"));
                trigger.setAttribute("aria-expanded", "false");
                if (panel) {
                    panel.hidden = true;
                }
            });
        }

        triggers.forEach(function (trigger) {
            const panel = document.getElementById(trigger.getAttribute("aria-controls"));
            if (!panel) {
                return;
            }
            trigger.addEventListener("click", function () {
                const willOpen = panel.hidden;
                closeAll(trigger);
                panel.hidden = !willOpen;
                trigger.setAttribute("aria-expanded", willOpen ? "true" : "false");
            });
        });

        document.addEventListener("pointerdown", function (event) {
            if (!root.contains(event.target)) {
                closeAll();
            }
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                closeAll();
            }
        });
    }

    function initProfilePlaceSearch() {
        const input = document.querySelector("[data-profile-place-search]");
        const grid = document.querySelector("[data-profile-place-grid]");
        if (!input || !grid) {
            return;
        }
        const cards = Array.from(grid.querySelectorAll(".profile-place-card"));
        const empty = document.querySelector("[data-profile-place-empty]");

        function applyFilter() {
            const query = input.value.trim().toLowerCase();
            let visibleCount = 0;
            cards.forEach(function (card) {
                const haystack = (card.dataset.placeSearch || card.textContent || "").toLowerCase();
                const visible = !query || haystack.indexOf(query) !== -1;
                card.hidden = !visible;
                if (visible) {
                    visibleCount += 1;
                }
            });
            if (empty) {
                empty.hidden = visibleCount !== 0;
            }
        }

        input.addEventListener("input", applyFilter);
        applyFilter();
    }

    initDiaryFeedMemory();
    initDiaryBackLink();
    initDeferredDiaryImages();
    initDiaryGallery();
    initCommentDrafts();
    initDiaryVideoGeneration();
    initDiaryInfiniteScroll();
    initIndoorRoutePicker();
    initCompactDatalists();
    initPlaceTagPopovers();
    initProfilePlaceSearch();

    layoutMasonryFeeds();
    window.addEventListener("load", scheduleMasonryLayout);
    window.addEventListener("resize", function () {
        scheduleMasonryLayout();
    });

    const messages = document.querySelectorAll(".message");
    messages.forEach(function (message) {
        setTimeout(function () {
            message.style.opacity = "0";
            message.style.transform = "translateY(-10px)";
            message.style.transition = "opacity 300ms ease, transform 300ms ease";
            setTimeout(function () {
                message.style.display = "none";
            }, 300);
        }, 3000);
    });
}());
