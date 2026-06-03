/**
 * Luxury Profile Premium Dynamics JavaScript
 *
 * Features:
 * 1. Narrative Thread scroll growth & bead positioning.
 * 2. High-precision 3D magnetic instrument rotation (with linear interpolation damping).
 * 3. Damped stats numeric growth counters (stats vials & mini counters).
 * 4. Micro-parallax image sliding for food cards.
 * 5. Staggered reveal animations for UI elements.
 */

document.addEventListener("DOMContentLoaded", () => {
    initPremiumReveals();
    initStatsCounters();
    initNarrativeThread();
    init3DAstrolabe();
    initFoodParallax();
    initTabSystem();
    initAvatarScrollWheel();
});

/**
 * 1. 元素延迟级联淡入入场 (Staggered Stagger Reveals)
 */
function initPremiumReveals() {
    const panels = document.querySelectorAll(".glass-panel");
    panels.forEach((panel, i) => {
        panel.style.animation = "fadeInUp 0.8s cubic-bezier(0.16, 1, 0.3, 1) both";
        panel.style.animationDelay = `${0.1 + i * 0.15}s`;
    });

    const cards = document.querySelectorAll(".glass-card, .profile-food-card, .chronicle-node");
    cards.forEach((card, i) => {
        card.style.animation = "fadeInUp 0.7s cubic-bezier(0.16, 1, 0.3, 1) both";
        card.style.animationDelay = `${0.2 + i * 0.08}s`;
    });
}

/**
 * 2. 数据滚动生长动效 (Kinetic Stats Counter)
 */
function initStatsCounters() {
    const counters = document.querySelectorAll(".profile-stats-horizon .lux-stat-value");
    counters.forEach(counter => {
        const targetText = counter.innerText.trim();
        const targetVal = parseFloat(targetText);
        if (isNaN(targetVal)) return;

        let startVal = 0;
        const duration = 1200; // 动效持续时间（毫秒）
        const stepTime = 16;
        const steps = duration / stepTime;
        const increment = targetVal / steps;
        const isDecimal = targetText.includes(".");

        let currentStep = 0;
        const timer = setInterval(() => {
            currentStep++;
            startVal += increment;

            if (currentStep >= steps) {
                counter.innerText = targetText;
                clearInterval(timer);
            } else {
                counter.innerText = isDecimal ? startVal.toFixed(1) : Math.floor(startVal);
            }
        }, stepTime);
    });
}

/**
 * 3. 叙事金线与金珠滚动流溢生长 (Narrative Thread Line)
 */
function initNarrativeThread() {
    const thread = document.querySelector(".narrative-line-glow");
    const bead = document.querySelector(".narrative-bead");
    const container = document.querySelector(".narrative-container");

    if (!thread || !bead || !container) return;

    // 前1秒星轨预热下探
    setTimeout(() => {
        thread.style.height = "120px";
        bead.style.top = "120px";
    }, 300);

    function updateThread() {
        const scrollTop = window.scrollY;
        const docHeight = document.documentElement.scrollHeight;
        const winHeight = window.innerHeight;

        const containerHeight = container.clientHeight;
        const scrollPercent = scrollTop / (docHeight - winHeight);

        // 阻尼映射高度（最大不超过容器高度，最小不少于120px）
        let targetHeight = scrollPercent * containerHeight;
        if (targetHeight < 120) targetHeight = 120;
        if (targetHeight > containerHeight) targetHeight = containerHeight;

        thread.style.height = `${targetHeight}px`;
        bead.style.top = `${targetHeight}px`;
    }

    window.addEventListener("scroll", updateThread, { passive: true });
    window.addEventListener("resize", updateThread, { passive: true });
}

/**
 * 4. 三维磁吸阻尼星盘 (High-Precision 3D Astrolabe / Compass Pointer)
 */
function init3DAstrolabe() {
    const compass = document.querySelector(".lux-compass-instrument");
    if (!compass) return;

    function renderAstrolabe() {
        const baseDrift = (Date.now() / 200) % 360;

        compass.style.transform = `
            perspective(600px)
            rotateZ(${baseDrift}deg)
        `;

        requestAnimationFrame(renderAstrolabe);
    }

    renderAstrolabe();
}

/**
 * 5. 美食图片反向平移微视差 (Parallax Translation)
 */
function initFoodParallax() {
    const foodCards = document.querySelectorAll(".profile-food-card");
    foodCards.forEach(card => {
        const img = card.querySelector("img");
        if (!img) return;

        card.addEventListener("mouseleave", () => {
            img.style.transform = `scale(1) translateX(0)`;
        });
    });
}

/**
 * 6. 高定玻璃分段选择器 Tab 切换系统 (Tab Switcher)
 */
function initTabSystem() {
    const triggers = document.querySelectorAll(".tab-trigger");
    const contents = document.querySelectorAll(".tab-content");

    triggers.forEach(trigger => {
        trigger.addEventListener("click", () => {
            const tabId = trigger.getAttribute("data-tab");
            if (!tabId) return;

            // 切换标签触发器的 active 态与 ARIA 属性
            triggers.forEach(t => {
                t.classList.remove("active");
                t.setAttribute("aria-selected", "false");
            });
            trigger.classList.add("active");
            trigger.setAttribute("aria-selected", "true");

            // 切换内容区域的显示
            contents.forEach(content => {
                content.classList.remove("active");
            });

            const activeContent = document.getElementById(`tab-content-${tabId}`);
            if (activeContent) {
                activeContent.classList.add("active");

                // 重置并触发内容卡片的 Stagger 延迟淡入动画
                const cards = activeContent.querySelectorAll(".glass-card, .profile-food-card, .chronicle-node");
                cards.forEach((card, i) => {
                    card.style.animation = "none";
                    void card.offsetHeight; // 强制浏览器重绘以重新触发关键帧动画
                    card.style.animation = "fadeInUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) both";
                    card.style.animationDelay = `${i * 0.05}s`;
                });
            }
        });
    });
}

/**
 * 7. 预设头像滑槽鼠标滚轮横向滚动映射 (Mouse Wheel Horizontal Scroll Mapper)
 */
function initAvatarScrollWheel() {
    const grid = document.querySelector(".avatar-picker__grid");
    if (!grid) return;

    grid.addEventListener("wheel", (e) => {
        // e.deltaY > 0 代表向下滚动，向右平移展示更多头像
        // e.deltaY < 0 代表向上滚动，向左平移展示更多头像
        if (e.deltaY !== 0) {
            e.preventDefault(); // 阻止整个页面的垂直滚动

            // 采用平滑缓动的 scrollBy (平滑滑移系数设置为 0.95)
            grid.scrollBy({
                left: e.deltaY * 0.95,
                behavior: "smooth"
            });
        }
    }, { passive: false }); // 必须显式声明 passive: false 才能阻止默认滚动
}
