(function () {
    const root = document.documentElement;
    const body = document.body;
    const interactiveSelector = ".menu-card, .action-card, .detail-card, .route-result, .node-card, .diary-card, .diary-form, .rating-form, .tag-box, .multi-target-box, .diary-post, .diary-search-form, .story-meta-chip, .compression-chip, .rating-bubble, .diary-gallery-stage, .comment-reply-sheet__panel";

    if (!body) {
        return;
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const isDiaryFeedPage = body.classList.contains("diary-list-page") || body.classList.contains("diary-search-page");
    const isFoodPage = body.classList.contains("food-product-page");
    if (!isDiaryFeedPage && !isFoodPage) {
        const orb = document.createElement("div");
        orb.className = "cursor-orb";
        orb.setAttribute("aria-hidden", "true");
        body.appendChild(orb);
    }

    let cursorX = window.innerWidth / 2;
    let cursorY = window.innerHeight * 0.35;
    let activeCard = null;
    let rafId = 0;
    let hoverTarget = null;
    let masonryRafId = 0;

    function paintCursor() {
        root.style.setProperty("--cursor-x", cursorX + "px");
        root.style.setProperty("--cursor-y", cursorY + "px");
    }

    function scheduleCursorPaint() {
        if (!rafId) {
            rafId = window.requestAnimationFrame(function () {
                paintCursor();
                updateHoverState(hoverTarget);
                rafId = 0;
            });
        }
    }

    function clearCardGlow(card) {
        if (!card) {
            return;
        }
        card.style.removeProperty("--card-x");
        card.style.removeProperty("--card-y");
    }

    function updateHoverState(target) {
        const nextCard = target && target.closest ? target.closest(interactiveSelector) : null;

        if (nextCard !== activeCard) {
            clearCardGlow(activeCard);
            activeCard = nextCard;
        }

        body.classList.toggle("is-hovering-ui", Boolean(nextCard));

        if (nextCard) {
            const rect = nextCard.getBoundingClientRect();
            nextCard.style.setProperty("--card-x", (cursorX - rect.left) + "px");
            nextCard.style.setProperty("--card-y", (cursorY - rect.top) + "px");
        }
    }

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

    function initDeferredDiaryImages() {
        const lazyImages = Array.from(document.querySelectorAll("img[data-diary-lazy-src]"));
        const lazyVideos = Array.from(document.querySelectorAll("video[data-diary-lazy-video]"));
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
            document.querySelectorAll("video[data-diary-lazy-video]").forEach(loadVideo);
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

        document.querySelectorAll(".comment-entry__content, .comment-composer, .comment-thread").forEach(function (node) {
            node.addEventListener("pointerenter", function () {
                body.classList.remove("is-hovering-ui");
                clearCardGlow(activeCard);
                activeCard = null;
            });
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && replySheet.classList.contains("is-open")) {
                closeReplySheet();
            }
        });
    }

    if (!reduceMotion && !isDiaryFeedPage && !isFoodPage) {
        window.addEventListener("pointermove", function (event) {
            cursorX = event.clientX;
            cursorY = event.clientY;
            hoverTarget = event.target;
            body.classList.add("is-pointer-active");
            scheduleCursorPaint();
        }, { passive: true });

        window.addEventListener("pointerleave", function () {
            body.classList.remove("is-pointer-active");
            body.classList.remove("is-hovering-ui");
            clearCardGlow(activeCard);
            activeCard = null;
        }, { passive: true });

        window.addEventListener("scroll", function () {
            if (activeCard) {
                clearCardGlow(activeCard);
                activeCard = null;
            }
            body.classList.remove("is-hovering-ui");
        }, { passive: true });
    }

    document.querySelectorAll(".js-masonry-feed img, .js-masonry-feed video").forEach(function (media) {
        media.addEventListener("load", scheduleMasonryLayout, { once: true });
        media.addEventListener("loadedmetadata", scheduleMasonryLayout, { once: true });
    });

    function initCanvasParticles() {
        if (reduceMotion || isDiaryFeedPage || isFoodPage) return;
        const canvas = document.createElement("canvas");
        canvas.id = "lux-particle-canvas";
        canvas.style.position = "fixed";
        canvas.style.top = "0";
        canvas.style.left = "0";
        canvas.style.width = "100%";
        canvas.style.height = "100%";
        canvas.style.zIndex = "-2";
        canvas.style.pointerEvents = "none";
        body.appendChild(canvas);

        const ctx = canvas.getContext("2d");
        let width = canvas.width = window.innerWidth;
        let height = canvas.height = window.innerHeight;

        const particles = [];
        const maxParticles = width < 768 ? 35 : 90;
        const connectionDist = 180;

        const mouse = {
            x: null,
            y: null,
            active: false
        };

        class Particle {
            constructor() {
                this.reset();
                this.y = Math.random() * height;
                this.x = Math.random() * width;
            }

            reset() {
                this.x = Math.random() * width;
                this.y = -10;
                this.radius = Math.random() * 1.5 + 1.2;
                this.baseVx = (Math.random() - 0.5) * 0.3;
                this.baseVy = Math.random() * 0.4 + 0.15; // slow drift down
                this.vx = this.baseVx;
                this.vy = this.baseVy;
                // Pastel translucent colors matching the light HSL theme
                const colors = [
                    "rgba(99, 102, 241, 0.28)",  // Indigo
                    "rgba(6, 182, 212, 0.28)",   // Cyan
                    "rgba(16, 185, 129, 0.25)",  // Emerald
                    "rgba(244, 63, 94, 0.25)",   // Rose
                    "rgba(139, 92, 246, 0.28)"   // Violet
                ];
                this.color = colors[Math.floor(Math.random() * colors.length)];
            }

            update() {
                this.x += this.vx;
                this.y += this.vy;

                if (mouse.active && mouse.x !== null && mouse.y !== null) {
                    const dx = mouse.x - this.x;
                    const dy = mouse.y - this.y;
                    const dist = Math.hypot(dx, dy);

                    if (dist < connectionDist) {
                        const force = (connectionDist - dist) / connectionDist;
                        // Magnetic tracking spring effect
                        this.vx += (dx / dist) * force * 0.14;
                        this.vy += (dy / dist) * force * 0.14;

                        // Connecting line
                        ctx.beginPath();
                        ctx.moveTo(this.x, this.y);
                        ctx.lineTo(mouse.x, mouse.y);
                        ctx.strokeStyle = `rgba(99, 102, 241, ${force * 0.14})`;
                        ctx.lineWidth = 0.65;
                        ctx.stroke();
                    }
                }

                // Damping
                this.vx *= 0.93;
                this.vy *= 0.93;

                // Drift retention
                this.vx += this.baseVx * 0.07;
                this.vy += this.baseVy * 0.07;

                // Border wraps/recreation
                if (this.y > height + 10 || this.x < -10 || this.x > width + 10) {
                    this.reset();
                }
            }

            draw() {
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
                ctx.fillStyle = this.color;
                ctx.fill();
            }
        }

        for (let i = 0; i < maxParticles; i++) {
            particles.push(new Particle());
        }

        window.addEventListener("pointermove", function (e) {
            mouse.x = e.clientX;
            mouse.y = e.clientY;
            mouse.active = true;
        }, { passive: true });

        window.addEventListener("pointerleave", function () {
            mouse.active = false;
        }, { passive: true });

        window.addEventListener("resize", function () {
            width = canvas.width = window.innerWidth;
            height = canvas.height = window.innerHeight;
        }, { passive: true });

        function animate() {
            ctx.clearRect(0, 0, width, height);

            for (let i = 0; i < particles.length; i++) {
                particles[i].update();
                particles[i].draw();
            }

            requestAnimationFrame(animate);
        }

        animate();
    }

    initDiaryFeedMemory();
    initDiaryBackLink();
    initDeferredDiaryImages();
    initDiaryGallery();
    initCommentDrafts();
    initCanvasParticles();

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
