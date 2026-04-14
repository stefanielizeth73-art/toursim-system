(function () {
    const root = document.documentElement;
    const body = document.body;

    if (!body || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        return;
    }

    const orb = document.createElement("div");
    orb.className = "cursor-orb";
    orb.setAttribute("aria-hidden", "true");
    body.appendChild(orb);

    let cursorX = window.innerWidth / 2;
    let cursorY = window.innerHeight * 0.35;
    let rafId = 0;

    function paintCursor() {
        root.style.setProperty("--cursor-x", cursorX + "px");
        root.style.setProperty("--cursor-y", cursorY + "px");
        rafId = 0;
    }

    function scheduleCursorPaint() {
        if (!rafId) {
            rafId = window.requestAnimationFrame(paintCursor);
        }
    }

    window.addEventListener("pointermove", function (event) {
        cursorX = event.clientX;
        cursorY = event.clientY;
        body.classList.add("is-pointer-active");
        scheduleCursorPaint();
    }, { passive: true });

    window.addEventListener("pointerleave", function () {
        body.classList.remove("is-pointer-active");
    }, { passive: true });

    const reactiveCards = document.querySelectorAll(
        ".menu-card, .action-card, .detail-card, .route-result, .node-card, .diary-card, .diary-form, .rating-form"
    );

    reactiveCards.forEach(function (card) {
        card.addEventListener("pointermove", function (event) {
            const rect = card.getBoundingClientRect();
            card.style.setProperty("--card-x", event.clientX - rect.left + "px");
            card.style.setProperty("--card-y", event.clientY - rect.top + "px");
        }, { passive: true });
    });

    // 自动隐藏提示消息
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

