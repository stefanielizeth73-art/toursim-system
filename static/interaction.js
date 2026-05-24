(function () {
    const root = document.documentElement;
    const body = document.body;
    const interactiveSelector = ".menu-card, .action-card, .detail-card, .route-result, .node-card, .diary-card, .diary-form, .rating-form, .tag-box, .multi-target-box, .diary-post, .diary-search-form, .story-meta-chip, .compression-chip, .rating-bubble, .diary-gallery-stage, .comment-reply-sheet__panel";

    if (!body) {
        return;
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const orb = document.createElement("div");
    orb.className = "cursor-orb";
    orb.setAttribute("aria-hidden", "true");
    body.appendChild(orb);

    let cursorX = window.innerWidth / 2;
    let cursorY = window.innerHeight * 0.35;
    let activeCard = null;
    let rafId = 0;
    let hoverTarget = null;

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
                    stage.style.backgroundImage = imageUrl ? "url('" + imageUrl.replace(/'/g, "\\'") + "')" : "none";
                    stage.style.backgroundRepeat = "no-repeat";
                    stage.style.backgroundPosition = "center center";
                    stage.style.backgroundSize = "contain";
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

    if (!reduceMotion) {
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
        media.addEventListener("load", layoutMasonryFeeds, { once: true });
        media.addEventListener("loadedmetadata", layoutMasonryFeeds, { once: true });
    });

    initDiaryFeedMemory();
    initDiaryBackLink();
    initDiaryGallery();
    initCommentDrafts();

    layoutMasonryFeeds();
    window.addEventListener("load", layoutMasonryFeeds);
    window.addEventListener("resize", function () {
        window.requestAnimationFrame(layoutMasonryFeeds);
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
