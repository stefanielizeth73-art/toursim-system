(function () {
    const body = document.body;
    if (!body || body.dataset.aiAssistantReady === "1") {
        return;
    }
    if (body.classList.contains("login-page") || body.classList.contains("register-page")) {
        return;
    }
    body.dataset.aiAssistantReady = "1";

    const state = {
        open: false,
        busy: false,
        historyLoaded: false,
        loadingHistory: false,
        conversationId: getStoredConversationId(),
    };

    function getStoredConversationId() {
        try {
            return window.localStorage ? localStorage.getItem("toursim-ai-conversation") || "" : "";
        } catch (error) {
            return "";
        }
    }

    function setStoredConversationId(conversationId) {
        try {
            if (window.localStorage && conversationId) {
                localStorage.setItem("toursim-ai-conversation", conversationId);
            }
        } catch (error) {
            // Storage can be unavailable in private browsing modes.
        }
    }

    function qs(name) {
        return new URLSearchParams(window.location.search).get(name) || "";
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
        return {
            page: currentPage(),
            path: window.location.pathname,
            place_id: body.dataset.placeId || qs("place_id") || "xmu_manual",
            start: qs("start") || qs("facility_start_node"),
            end: qs("end"),
            origin_node: qs("origin_node"),
            strategy: qs("strategy") || "distance",
            transport: qs("transport") || "walk",
            building_id: qs("building_id") || "demo_building",
            vertical_mode: qs("vertical_mode") || "auto",
        };
    }

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text) node.textContent = text;
        return node;
    }

    function appendMessage(role, text) {
        const item = el("div", "ai-assistant__message ai-assistant__message--" + role);
        item.textContent = text;
        messages.appendChild(item);
        messages.scrollTop = messages.scrollHeight;
        return item;
    }

    function appendProviderMeta(payload) {
        const provider = payload && payload.provider ? payload.provider : "local";
        const model = payload && payload.model ? payload.model : "";
        const error = payload && payload.model_error ? payload.model_error : "";
        const text = provider === "local"
            ? ("本地模式" + (error ? "，模型调用失败：" + error : ""))
            : (provider.charAt(0).toUpperCase() + provider.slice(1) + (model ? " · " + model : ""));
        const item = el("div", "ai-assistant__provider", text);
        messages.appendChild(item);
        messages.scrollTop = messages.scrollHeight;
    }

    function appendIntro() {
        appendMessage(
            "assistant",
            "你好，我是通用 AI 助手。普通聊天、解释、写作、建议都可以直接问；当我判断你需要 TourSim 的美食、景点、路线、室内导航或游记数据时，会自动先查系统结果再回答。"
        );
        renderSuggestions(conversationalSuggestions());
    }

    function renderCards(cards) {
        if (!cards || !cards.length) {
            return;
        }
        const wrap = el("div", "ai-assistant__cards");
        wrap.appendChild(el("div", "ai-assistant__cards-title", "我查到的几个备选"));
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
        if (!actions || !actions.length) {
            return;
        }
        const wrap = el("div", "ai-assistant__actions");
        actions.forEach(function (action) {
            const link = el("a", "ai-assistant__action", action.label || "打开");
            link.href = action.url || "#";
            wrap.appendChild(link);
        });
        messages.appendChild(wrap);
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
        if (state.historyLoaded || state.loadingHistory) {
            return messages.childElementCount > 0;
        }
        state.loadingHistory = true;
        try {
            const suffix = state.conversationId ? "?conversation_id=" + encodeURIComponent(state.conversationId) : "";
            const response = await fetch("/api/assistant/history" + suffix, {
                method: "GET",
                credentials: "same-origin",
            });
            if (!response.ok) {
                return false;
            }
            const payload = await response.json();
            if (payload.conversation_id) {
                state.conversationId = payload.conversation_id;
                setStoredConversationId(state.conversationId);
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
    }

    function defaultSuggestions() {
        const page = currentPage();
        if (page === "foods") return ["按当前位置推荐吃饭", "预算15元以内", "找评分高的食堂", "帮我规划吃饭路线"];
        if (page === "route") return ["帮我解释当前路线", "附近有什么设施", "规划三点游览", "路线后推荐吃饭"];
        if (page === "indoor") return ["只坐电梯怎么走", "换成走楼梯", "解释当前室内路线", "回到大门"];
        if (page === "diaries") return ["找拍照攻略", "参考热门日记", "适合半日游吗", "推荐相关地点"];
        return ["推荐一条校园路线", "现在吃什么", "找几篇游记", "室内怎么导航"];
    }

    function conversationalSuggestions() {
        const page = currentPage();
        if (page === "foods") return ["聊聊今天吃什么", "帮我查校园美食推荐", "食堂预算15元内", "吃完顺路去哪"];
        if (page === "route") return ["随便问个问题", "帮我做路线规划", "规划三点一线", "走完再吃什么"];
        if (page === "indoor") return ["随便聊聊", "触发室内导航", "只坐电梯怎么走", "解释一个概念"];
        if (page === "diaries") return ["帮我润色一段话", "找几篇游记攻略", "半日游怎么安排", "按游记推荐地点"];
        return ["随便聊聊", "帮我解释一个概念", "帮我查校园美食推荐", "帮我做路线规划"];
    }

    async function sendMessage() {
        const message = input.value.trim();
        if (!message || state.busy) {
            return;
        }
        state.busy = true;
        input.value = "";
        sendButton.disabled = true;
        appendMessage("user", message);
        const loading = el("div", "ai-assistant__message ai-assistant__message--assistant is-loading", "正在整理建议...");
        messages.appendChild(loading);
        loading.textContent = "我查一下系统里的数据，顺手帮你捋一捋...";

        try {
            const response = await fetch("/api/assistant/chat", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                credentials: "same-origin",
                body: JSON.stringify({
                    message: message,
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
            setStoredConversationId(state.conversationId);
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

    const launcher = el("button", "ai-assistant-launcher", "AI");
    launcher.type = "button";
    launcher.setAttribute("aria-label", "打开 AI 旅游助手");

    const panel = el("section", "ai-assistant");
    panel.setAttribute("aria-label", "AI 旅游助手");
    panel.innerHTML = [
        '<header class="ai-assistant__head">',
        '<div><span>TourSim AI</span><strong>个性化助手</strong></div>',
        '<button type="button" class="ai-assistant__close" aria-label="关闭 AI 助手">×</button>',
        '</header>',
        '<div class="ai-assistant__messages" role="log" aria-live="polite"></div>',
        '<div class="ai-assistant__chips" aria-label="快捷提问"></div>',
        '<form class="ai-assistant__form">',
        '<input type="text" maxlength="600" placeholder="问我吃什么、怎么走、看什么..." aria-label="输入你的旅行需求">',
        '<button type="submit">发送</button>',
        '</form>',
    ].join("");

    const messages = panel.querySelector(".ai-assistant__messages");
    const chips = panel.querySelector(".ai-assistant__chips");
    const form = panel.querySelector(".ai-assistant__form");
    const input = form.querySelector("input");
    const sendButton = form.querySelector("button");
    const closeButton = panel.querySelector(".ai-assistant__close");
    const title = panel.querySelector(".ai-assistant__head strong");
    if (title) {
        title.textContent = "通用 AI 助手";
    }
    if (input) {
        input.placeholder = "普通问题直接问；系统联动说“校园美食/路线规划”...";
    }
    if (sendButton) {
        sendButton.textContent = "发送";
    }

    if (title) {
        title.textContent = "像同学一样帮你参谋";
    }
    if (input) {
        input.placeholder = "直接说你的想法：饿了、想逛、赶时间、问问题...";
    }
    if (sendButton) {
        sendButton.textContent = "发送";
    }

    function setOpen(open) {
        state.open = open;
        panel.classList.toggle("is-open", open);
        launcher.classList.toggle("is-hidden", open);
        if (open && messages.childElementCount === 0) {
            const loadingHistory = el("div", "ai-assistant__message ai-assistant__message--assistant is-loading", "正在找回上次聊天...");
            messages.appendChild(loadingHistory);
            loadHistory().then(function (hasHistory) {
                loadingHistory.remove();
                if (!hasHistory && messages.childElementCount === 0) {
                    appendIntro();
                }
            });
        }
        if (open && messages.childElementCount === 0) {
            appendMessage("assistant", "告诉我你的时间、预算、位置或偏好，我会结合本系统的景点、美食、路线、室内导航和日记数据给出建议。");
            if (messages.lastElementChild) {
                messages.lastElementChild.textContent = "你好，我是通用 AI 助手。普通聊天、解释、写作、建议都可以直接问；只有你明确说到“校园美食”“路线规划”“室内导航”“游记攻略”等关键词时，我才会联动 TourSim 里的系统数据。";
            }
            renderSuggestions(conversationalSuggestions());
        }
        if (open) {
            input.focus();
        }
    }

    launcher.addEventListener("click", function () { setOpen(true); });
    closeButton.addEventListener("click", function () { setOpen(false); });
    form.addEventListener("submit", function (event) {
        event.preventDefault();
        sendMessage();
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && state.open) {
            setOpen(false);
        }
    });

    document.body.appendChild(launcher);
    document.body.appendChild(panel);
}());
