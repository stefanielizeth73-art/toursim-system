(function () {
    const body = document.body;
    if (!body || body.dataset.aiAssistantReady === "1") return;
    if (body.classList.contains("login-page") || body.classList.contains("register-page")) return;
    body.dataset.aiAssistantReady = "1";

    const storageKeys = {
        conversation: "toursim-ai-conversation",
        position: "toursim-ai-position",
        size: "toursim-ai-size",
        suggestionsCollapsed: "toursim-ai-suggestions-collapsed"
    };

    const state = {
        open: false,
        busy: false,
        historyLoaded: false,
        loadingHistory: false,
        conversationId: readStorage(storageKeys.conversation) || "",
        position: readJsonStorage(storageKeys.position),
        size: readSizeStorage(storageKeys.size),
        suggestionsCollapsed: readStorage(storageKeys.suggestionsCollapsed) !== "0"
    };

    function readStorage(key) {
        try {
            return window.localStorage ? localStorage.getItem(key) : "";
        } catch (error) {
            return "";
        }
    }

    function writeStorage(key, value) {
        try {
            if (window.localStorage && value) localStorage.setItem(key, value);
        } catch (error) {
            // Storage can be unavailable in private browsing modes.
        }
    }

    function removeStorage(key) {
        try {
            if (window.localStorage) localStorage.removeItem(key);
        } catch (error) {
            // Storage can be unavailable in private browsing modes.
        }
    }

    function readJsonStorage(key) {
        const raw = readStorage(key);
        if (!raw) return null;
        try {
            const value = JSON.parse(raw);
            return Number.isFinite(value.x) && Number.isFinite(value.y) ? value : null;
        } catch (error) {
            return null;
        }
    }

    function readSizeStorage(key) {
        const raw = readStorage(key);
        if (!raw) return null;
        try {
            const value = JSON.parse(raw);
            return Number.isFinite(value.height) ? value : null;
        } catch (error) {
            return null;
        }
    }

    function writePosition(position) {
        state.position = position;
        writeStorage(storageKeys.position, JSON.stringify(position));
    }

    function writeSize(size) {
        state.size = size;
        writeStorage(storageKeys.size, JSON.stringify(size));
    }

    function setSuggestionsCollapsed(collapsed) {
        state.suggestionsCollapsed = collapsed;
        writeStorage(storageKeys.suggestionsCollapsed, collapsed ? "1" : "0");
        updateSuggestionsVisibility();
    }

    function qs(name) {
        return new URLSearchParams(window.location.search).get(name) || "";
    }

    function selectedText(select) {
        if (!select || !select.options || select.selectedIndex < 0) return "";
        return select.options[select.selectedIndex].textContent.trim();
    }

    function currentPage() {
        const path = window.location.pathname;
        if (path.indexOf("/foods") === 0 || path.indexOf("/food/") === 0) return "foods";
        if (path.indexOf("/route") === 0 || path.indexOf("/facilities") === 0) return "route";
        if (path.indexOf("/indoor") === 0) return "indoor";
        if (path.indexOf("/diaries") === 0 || path.indexOf("/diary/") === 0) return "diaries";
        if (path.indexOf("/places") === 0 || path.indexOf("/place/") === 0) return "places";
        if (path.indexOf("/profile") === 0 || path.indexOf("/user/") === 0) return "profile";
        return "home";
    }

    function pageContext() {
        const startSelect = document.getElementById("startNode");
        const endSelect = document.getElementById("endNode");
        const transportSelect = document.getElementById("transport");
        return {
            page: currentPage(),
            path: window.location.pathname,
            place_id: body.dataset.placeId || qs("place_id") || "xmu_manual",
            start: qs("start") || qs("facility_start_node") || (startSelect && startSelect.value) || "",
            start_name: selectedText(startSelect),
            end: qs("end") || (endSelect && endSelect.value) || "",
            end_name: selectedText(endSelect),
            origin_node: qs("origin_node"),
            strategy: qs("strategy") || "distance",
            transport: qs("transport") || (transportSelect && transportSelect.value) || "mixed",
            building_id: qs("building_id") || "demo_building",
            vertical_mode: qs("vertical_mode") || "auto",
        };
    }

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = text;
        return node;
    }

    function appendMessage(role, text) {
        const item = el("div", "ai-assistant__message ai-assistant__message--" + role);
        item.textContent = text || "";
        messages.appendChild(item);
        messages.scrollTop = messages.scrollHeight;
        return item;
    }

    function appendProviderMeta(payload) {
        const provider = payload && payload.provider ? payload.provider : "local";
        const model = payload && payload.model ? payload.model : "";
        const error = payload && payload.model_error ? payload.model_error : "";
        const text = provider === "local"
            ? ("本地检索" + (error ? "，模型暂时没接上：" + error : ""))
            : (provider.charAt(0).toUpperCase() + provider.slice(1) + (model ? " · " + model : ""));
        messages.appendChild(el("div", "ai-assistant__provider", text));
        messages.scrollTop = messages.scrollHeight;
    }

    function appendIntro() {
        appendMessage(
            "assistant",
            "我在。你可以直接说想吃什么、从哪到哪、想找哪类游记，或者只是随便问问题。我会自己判断要不要翻 TourSim 里的美食、路线、室内导航和日记。"
        );
        renderSuggestions(conversationalSuggestions());
    }

    function renderCards(cards) {
        if (!cards || !cards.length) return;
        const wrap = el("div", "ai-assistant__cards");
        wrap.appendChild(el("div", "ai-assistant__cards-title", "可以直接点开的结果"));
        cards.forEach(function (card) {
            const link = el("a", "ai-assistant__card");
            link.href = card.url || "#";
            if (card.image) {
                const img = el("img", "ai-assistant__card-image");
                img.src = "/static/" + card.image;
                img.alt = card.title || "";
                link.appendChild(img);
            }
            const content = el("span", "ai-assistant__card-body");
            content.appendChild(el("strong", "", card.title || "推荐"));
            if (card.subtitle) content.appendChild(el("small", "", card.subtitle));
            if (card.description) content.appendChild(el("span", "ai-assistant__card-desc", card.description));
            link.appendChild(content);
            wrap.appendChild(link);
        });
        messages.appendChild(wrap);
        messages.scrollTop = messages.scrollHeight;
    }

    function renderActions(actions) {
        if (!actions || !actions.length) return;
        const wrap = el("div", "ai-assistant__actions");
        actions.forEach(function (action) {
            const node = action.command ? el("button", "ai-assistant__action", action.label || "执行") : el("a", "ai-assistant__action", action.label || "打开");
            if (action.command) {
                node.type = "button";
                node.addEventListener("click", function () {
                    handleAssistantAction(action);
                });
            } else {
                node.href = action.url || "#";
            }
            wrap.appendChild(node);
        });
        messages.appendChild(wrap);
        messages.scrollTop = messages.scrollHeight;
    }

    function renderHistory(items) {
        messages.innerHTML = "";
        (items || []).forEach(function (item) {
            appendMessage(item.role === "user" ? "user" : "assistant", item.content || "");
            if (item.role === "assistant" && item.metadata) {
                appendProviderMeta(item.metadata);
                renderCards(item.metadata.cards);
                renderActions(item.metadata.actions);
            }
        });
        renderSuggestions(conversationalSuggestions());
    }

    async function loadHistory() {
        if (state.historyLoaded || state.loadingHistory) return messages.childElementCount > 0;
        state.loadingHistory = true;
        try {
            const suffix = state.conversationId ? "?conversation_id=" + encodeURIComponent(state.conversationId) : "";
            const response = await fetch("/api/assistant/history" + suffix, { credentials: "same-origin" });
            if (!response.ok) return false;
            const payload = await response.json();
            if (payload.conversation_id) {
                state.conversationId = payload.conversation_id;
                writeStorage(storageKeys.conversation, state.conversationId);
            }
            if (payload.messages && payload.messages.length) {
                renderHistory(payload.messages);
                return true;
            }
            return false;
        } catch (error) {
            return false;
        } finally {
            state.historyLoaded = true;
            state.loadingHistory = false;
        }
    }

    function renderSuggestions(suggestions) {
        chips.innerHTML = "";
        (suggestions || conversationalSuggestions()).slice(0, 4).forEach(function (suggestion) {
            const button = el("button", "ai-assistant__chip", suggestion);
            button.type = "button";
            button.addEventListener("click", function () {
                input.value = suggestion;
                sendMessage();
            });
            chips.appendChild(button);
        });
        updateSuggestionsVisibility();
    }

    function updateSuggestionsVisibility() {
        if (!panel || !chipsToggle) return;
        panel.classList.toggle("are-suggestions-hidden", state.suggestionsCollapsed);
        chipsToggle.textContent = state.suggestionsCollapsed ? "显示快捷建议" : "隐藏快捷建议";
        chipsToggle.setAttribute("aria-expanded", state.suggestionsCollapsed ? "false" : "true");
    }

    function newConversation() {
        state.conversationId = createConversationId();
        writeStorage(storageKeys.conversation, state.conversationId);
        state.historyLoaded = true;
        state.loadingHistory = false;
        messages.innerHTML = "";
        appendIntro();
        input.focus();
    }

    function createConversationId() {
        if (window.crypto && typeof crypto.randomUUID === "function") return crypto.randomUUID();
        return "local-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
    }

    function conversationalSuggestions() {
        const page = currentPage();
        if (page === "foods") return ["想吃清淡点", "按距离帮我筛", "人均低一点", "吃完顺路去哪"];
        if (page === "route") return ["从大门到图书馆", "默认混合交通规划", "少走路一点", "顺路找吃的"];
        if (page === "indoor") return ["只坐电梯怎么走", "换成楼梯路线", "解释当前路线", "回到大门"];
        if (page === "diaries") return ["找拍照攻略", "搜高分游记", "帮我润色日记", "按目的地筛"];
        return ["随便聊聊", "想吃清淡点", "从大门到图书馆", "找几篇拍照游记"];
    }

    function buildUrl(path, params) {
        const url = new URL(path, window.location.origin);
        Object.entries(params || {}).forEach(function ([key, value]) {
            if (value !== "" && value != null) url.searchParams.set(key, value);
        });
        return url.pathname + url.search;
    }

    function setField(form, name, value) {
        if (!form || value == null || value === "") return;
        const safeName = window.CSS && CSS.escape ? CSS.escape(name) : name.replace(/"/g, "");
        let field = form.querySelector(`[name="${safeName}"]`);
        if (!field) {
            field = document.createElement("input");
            field.type = "hidden";
            field.name = name;
            form.appendChild(field);
        }
        field.value = value;
    }

    function submitForm(form) {
        if (!form) return false;
        if (form.requestSubmit) form.requestSubmit();
        else form.submit();
        return true;
    }

    function handleAssistantAction(action) {
        const command = action.command || {};
        const params = command.params || {};
        if (command.type === "route_plan") {
            if (currentPage() === "route") {
                const form = document.getElementById("routePlanner");
                setField(form, "route_type", params.route_type || "single");
                setField(form, "start", params.start);
                setField(form, "end", params.end);
                setField(form, "strategy", params.strategy || "distance");
                setField(form, "transport", params.transport || "mixed");
                appendMessage("assistant", "我已经把起点、终点和混合交通填好了，正在让地图高亮路线。");
                submitForm(form);
                return;
            }
            window.location.href = action.url || buildUrl("/route", params);
            return;
        }
        if (command.type === "food_filter") {
            if (currentPage() === "foods") {
                const form = document.querySelector(".foods-filter-form");
                setField(form, "place_id", params.place_id || body.dataset.placeId || "xmu_manual");
                setField(form, "keyword", params.keyword || "");
                setField(form, "category", params.category || "");
                setField(form, "sort_by", params.sort_by || "recommend_score_desc");
                setField(form, "origin_node", params.origin_node || "");
                appendMessage("assistant", "我已经替你套用筛选条件。");
                submitForm(form);
                return;
            }
            window.location.href = action.url || buildUrl("/foods", params);
            return;
        }
        if (command.type === "diary_search") {
            const form = document.querySelector("form.diary-search-controlbar") || document.querySelector("form.diary-search-form");
            if (currentPage() === "diaries" && form) {
                setField(form, "q", params.keyword || params.q || "");
                setField(form, "keyword", params.keyword || params.q || "");
                setField(form, "destination", params.destination || "");
                setField(form, "sort_by", params.sort_by || "hot_rating_desc");
                appendMessage("assistant", "我来按这个方向筛日记。");
                submitForm(form);
                return;
            }
            window.location.href = action.url || buildUrl("/diaries/search", params);
            return;
        }
        if (command.type === "place_filter") {
            window.location.href = action.url || buildUrl("/places", params);
            return;
        }
        if (action.url) window.location.href = action.url;
    }

    async function sendMessage() {
        const message = input.value.trim();
        if (!message || state.busy) return;
        state.busy = true;
        input.value = "";
        sendButton.disabled = true;
        appendMessage("user", message);
        const loading = el("div", "ai-assistant__message ai-assistant__message--assistant is-loading", "我看一下上下文和本地数据...");
        messages.appendChild(loading);

        try {
            const response = await fetch("/api/assistant/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                    message,
                    conversation_id: state.conversationId,
                    page_context: pageContext(),
                }),
            });
            const payload = await response.json();
            loading.remove();
            if (!response.ok) {
                appendMessage("assistant", payload.error || "助手暂时不可用。");
                return;
            }
            state.conversationId = payload.conversation_id || state.conversationId;
            writeStorage(storageKeys.conversation, state.conversationId);
            appendMessage("assistant", payload.answer || "我整理好了一些建议。");
            appendProviderMeta(payload);
            renderCards(payload.cards);
            renderActions(payload.actions);
            renderSuggestions(payload.suggestions);
        } catch (error) {
            loading.remove();
            appendMessage("assistant", "网络连接不稳定，稍后再试一次。");
        } finally {
            state.busy = false;
            sendButton.disabled = false;
            input.focus();
        }
    }

    function clampPosition(x, y, node) {
        const rect = node.getBoundingClientRect();
        const width = rect.width || (node.classList.contains("ai-assistant") ? 420 : 56);
        const height = rect.height || (node.classList.contains("ai-assistant") ? 680 : 56);
        const margin = 10;
        return {
            x: Math.max(margin, Math.min(window.innerWidth - width - margin, x)),
            y: Math.max(margin, Math.min(window.innerHeight - height - margin, y))
        };
    }

    function clampHeight(height) {
        const minHeight = Math.min(360, window.innerHeight - 24);
        const maxHeight = Math.max(minHeight, window.innerHeight - 20);
        return Math.max(minHeight, Math.min(maxHeight, height));
    }

    function applySize(node) {
        if (!state.size || !node.classList.contains("ai-assistant")) return;
        node.style.height = clampHeight(state.size.height) + "px";
    }

    function applyPosition(node) {
        if (!state.position) {
            node.style.left = "";
            node.style.top = "";
            node.style.right = "";
            node.style.bottom = "";
            return;
        }
        const pos = clampPosition(state.position.x, state.position.y, node);
        node.style.left = pos.x + "px";
        node.style.top = pos.y + "px";
        node.style.right = "auto";
        node.style.bottom = "auto";
    }

    function makeVerticalResizable(node, handle, edge) {
        let resize = null;
        function moveResize(event) {
            if (!resize || event.pointerId !== resize.pointerId) return;
            event.preventDefault();
            const margin = 10;
            let height = resize.height;
            let top = resize.top;
            if (edge === "top") {
                const bottom = resize.top + resize.height;
                height = clampHeight(bottom - event.clientY);
                top = Math.max(margin, Math.min(window.innerHeight - height - margin, bottom - height));
            } else {
                height = clampHeight(event.clientY - resize.top);
            }
            writeSize({ height });
            node.style.height = height + "px";
            if (edge === "top") {
                writePosition(clampPosition(resize.left, top, node));
                applyPosition(node);
            }
            node.classList.add("is-resizing");
        }
        function stopResize(event) {
            if (!resize || event.pointerId !== resize.pointerId) return;
            resize = null;
            node.classList.remove("is-resizing");
            document.removeEventListener("pointermove", moveResize);
            document.removeEventListener("pointerup", stopResize);
            document.removeEventListener("pointercancel", stopResize);
        }
        handle.addEventListener("pointerdown", function (event) {
            if (event.button !== 0) return;
            const rect = node.getBoundingClientRect();
            if (!state.position) {
                writePosition(clampPosition(rect.left, rect.top, node));
                applyPosition(node);
            }
            resize = {
                pointerId: event.pointerId,
                left: rect.left,
                top: rect.top,
                height: rect.height
            };
            event.preventDefault();
            document.addEventListener("pointermove", moveResize);
            document.addEventListener("pointerup", stopResize);
            document.addEventListener("pointercancel", stopResize);
        });
    }

    function makeDraggable(node, handle) {
        let drag = null;
        function moveDrag(event) {
            if (!drag || event.pointerId !== drag.pointerId) return;
            const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
            if (!drag.moved && distance < 6) return;
            drag.moved = true;
            event.preventDefault();
            node.classList.add("is-dragging");
            const pos = clampPosition(event.clientX - drag.dx, event.clientY - drag.dy, node);
            writePosition(pos);
            applyPosition(node);
        }
        function stopDrag(event) {
            if (!drag || event.pointerId !== drag.pointerId) return;
            if (drag.moved) {
                node.dataset.aiDragged = "1";
                if (node === panel) panel.dataset.aiPanelMoved = "1";
            }
            drag = null;
            node.classList.remove("is-dragging");
            document.removeEventListener("pointermove", moveDrag);
            document.removeEventListener("pointerup", stopDrag);
            document.removeEventListener("pointercancel", stopDrag);
        }
        handle.addEventListener("pointerdown", function (event) {
            if (event.button !== 0) return;
            const target = event.target;
            const interactive = target.closest("button, a, input, textarea, select");
            if (interactive && interactive !== handle) return;
            const rect = node.getBoundingClientRect();
            drag = {
                dx: event.clientX - rect.left,
                dy: event.clientY - rect.top,
                startX: event.clientX,
                startY: event.clientY,
                pointerId: event.pointerId,
                moved: false
            };
            event.preventDefault();
            document.addEventListener("pointermove", moveDrag);
            document.addEventListener("pointerup", stopDrag);
            document.addEventListener("pointercancel", stopDrag);
        });
    }

    const launcher = el("button", "ai-assistant-launcher", "AI");
    launcher.type = "button";
    launcher.setAttribute("aria-label", "打开 AI 助手");

    const panel = el("section", "ai-assistant");
    panel.setAttribute("aria-label", "AI 助手");
    panel.innerHTML = [
        '<span class="ai-assistant__resize ai-assistant__resize--top" aria-hidden="true"></span>',
        '<header class="ai-assistant__head">',
        '<div><span>TourSim AI</span><strong>像同学一样帮你参谋</strong></div>',
        '<div class="ai-assistant__head-actions">',
        '<button type="button" class="ai-assistant__new">新对话</button>',
        '<button type="button" class="ai-assistant__close" aria-label="关闭 AI 助手">×</button>',
        '</div>',
        '</header>',
        '<div class="ai-assistant__messages" role="log" aria-live="polite"></div>',
        '<div class="ai-assistant__suggestionbar"><span>快捷建议</span><button type="button" class="ai-assistant__chips-toggle" aria-expanded="false">显示快捷建议</button></div>',
        '<div class="ai-assistant__chips" aria-label="快捷提问"></div>',
        '<form class="ai-assistant__form">',
        '<input type="text" maxlength="600" placeholder="直接说：饿了、想逛、从哪到哪..." aria-label="输入你的需求">',
        '<button type="submit">发送</button>',
        '</form>',
        '<span class="ai-assistant__resize ai-assistant__resize--bottom" aria-hidden="true"></span>',
    ].join("");

    const messages = panel.querySelector(".ai-assistant__messages");
    const chips = panel.querySelector(".ai-assistant__chips");
    const form = panel.querySelector(".ai-assistant__form");
    const input = form.querySelector("input");
    const sendButton = form.querySelector("button");
    const closeButton = panel.querySelector(".ai-assistant__close");
    const newButton = panel.querySelector(".ai-assistant__new");
    const chipsToggle = panel.querySelector(".ai-assistant__chips-toggle");
    const head = panel.querySelector(".ai-assistant__head");
    const resizeTop = panel.querySelector(".ai-assistant__resize--top");
    const resizeBottom = panel.querySelector(".ai-assistant__resize--bottom");

    function setOpen(open) {
        state.open = open;
        panel.classList.toggle("is-open", open);
        launcher.classList.toggle("is-hidden", open);
        applySize(panel);
        applyPosition(open ? panel : launcher);
        if (open && messages.childElementCount === 0) {
            const loadingHistory = el("div", "ai-assistant__message ai-assistant__message--assistant is-loading", "正在找回上次聊天...");
            messages.appendChild(loadingHistory);
            loadHistory().then(function (hasHistory) {
                loadingHistory.remove();
                if (!hasHistory && messages.childElementCount === 0) appendIntro();
            });
        }
        if (open) input.focus();
    }

    launcher.addEventListener("click", function () {
        if (launcher.dataset.aiDragged === "1") {
            launcher.dataset.aiDragged = "0";
            return;
        }
        setOpen(true);
    });
    newButton.addEventListener("click", newConversation);
    chipsToggle.addEventListener("click", function () {
        setSuggestionsCollapsed(!state.suggestionsCollapsed);
    });
    closeButton.addEventListener("click", function () {
        if (panel.dataset.aiPanelMoved === "1") {
            const rect = panel.getBoundingClientRect();
            writePosition(clampPosition(rect.left, rect.top, launcher));
        }
        setOpen(false);
    });
    form.addEventListener("submit", function (event) {
        event.preventDefault();
        sendMessage();
    });
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && state.open) setOpen(false);
    });
    window.addEventListener("resize", function () {
        applyPosition(state.open ? panel : launcher);
    });

    document.body.appendChild(launcher);
    document.body.appendChild(panel);
    updateSuggestionsVisibility();
    applySize(panel);
    applyPosition(launcher);
    makeDraggable(launcher, launcher);
    makeDraggable(panel, head);
    makeVerticalResizable(panel, resizeTop, "top");
    makeVerticalResizable(panel, resizeBottom, "bottom");
}());
