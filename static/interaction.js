(function () {
    const root = document.documentElement;
    const body = document.body;
    const interactiveSelector = ".menu-card, .action-card, .detail-card, .route-result, .node-card, .diary-card, .diary-form, .rating-form, .tag-box, .multi-target-box";

    if (!body || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        return;
    }

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

