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
 * 4. 经典奢华罗盘方位跟踪与 3D 动力学交互 (Classic Luxury Compass Interaction)
 */
function init3DAstrolabe() {
    const compassAnchor = document.querySelector(".lux-compass-anchor");
    const compass = document.querySelector(".lux-compass-instrument");
    const compassPointer = document.querySelector(".compass-pointer");
    const compassDial = document.querySelector(".compass-dial");

    if (!compassAnchor) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let targetAngle = 0;
    let currentAngle = 0;
    let targetTiltX = 0;
    let targetTiltY = 0;
    let currentTiltX = 0;
    let currentTiltY = 0;
    let isInteracting = false;
    let isSpinning = false;
    let spinStart = 0;
    let lastMoveTime = Date.now();

    const quotes = [
        "🧭 寻找您的专属旅行灵感中...",
        "🧭 探索未知，见所未见。",
        "🧭 行者无疆，始于足下。",
        "🧭 开启您的尊贵定制航线～",
        "🧭 读万卷书，行万里路。",
        "🧭 愿每次出发，都有温暖相伴。",
        "🧭 听从内心的罗盘，即刻启程！"
    ];

    // 动态创建气泡
    let bubble = document.createElement("div");
    bubble.className = "eye-bubble";
    compassAnchor.appendChild(bubble);

    document.addEventListener("mousemove", (event) => {
        if (!compass || reduceMotion) return;
        isInteracting = true;
        lastMoveTime = Date.now();

        const rect = compass.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const dx = event.clientX - centerX;
        const dy = event.clientY - centerY;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist > 15) {
            const angleRad = Math.atan2(dy, dx);
            // 默认指向上方是-90度，所以指针需要旋转 angleRad * 180/PI + 90 度
            targetAngle = angleRad * (180 / Math.PI) + 90;

            // 计算3D倾斜视角：绕X/Y轴微倾斜
            const maxDist = 300;
            const factorX = Math.min(Math.abs(dy) / maxDist, 1) * Math.sign(dy);
            const factorY = Math.min(Math.abs(dx) / maxDist, 1) * Math.sign(dx);
            targetTiltX = -factorX * 15;
            targetTiltY = factorY * 15;
        }
    });

    document.addEventListener("mouseleave", () => {
        isInteracting = false;
        targetTiltX = 0;
        targetTiltY = 0;
    });

    // 点击罗盘触发 3D 特技空转
    compassAnchor.addEventListener("click", () => {
        if (isSpinning) return;

        isSpinning = true;
        spinStart = performance.now();

        const randomQuote = quotes[Math.floor(Math.random() * quotes.length)];
        bubble.innerText = randomQuote;
        bubble.classList.add("show");

        setTimeout(() => {
            bubble.classList.remove("show");
        }, 1800);
    });

    function updateCompass(now) {
        if (!reduceMotion) {
            const lerpFactor = 0.06;

            if (isSpinning) {
                const progress = Math.min((now - spinStart) / 1200, 1);
                if (progress >= 1) {
                    isSpinning = false;
                } else {
                    // 快速旋转两圈 (720度) 并伴随缓出
                    const easeOutQuad = 1 - (1 - progress) * (1 - progress);
                    currentAngle = targetAngle + easeOutQuad * 720;
                    currentTiltX = Math.sin(progress * Math.PI * 2) * 5;
                    currentTiltY = Math.cos(progress * Math.PI * 2) * 5;
                }
            } else {
                // 顺滑 Lerp 跟随 (并处理 360 度边界突变)
                let diff = targetAngle - currentAngle;
                const diffRad = (diff * Math.PI) / 180;
                const wrappedDiff = Math.atan2(Math.sin(diffRad), Math.cos(diffRad)) * 180 / Math.PI;
                currentAngle += wrappedDiff * lerpFactor;

                currentTiltX += (targetTiltX - currentTiltX) * lerpFactor;
                currentTiltY += (targetTiltY - currentTiltY) * lerpFactor;

                // 鼠标空闲时的微小呼吸自摆动动画
                const timeSinceLastMove = Date.now() - lastMoveTime;
                const isIdle = timeSinceLastMove > 2500 || !isInteracting;
                if (isIdle) {
                    const idleTime = now / 1200;
                    targetAngle = Math.sin(idleTime) * 15;
                    targetTiltX = Math.sin(idleTime * 0.8) * 3;
                    targetTiltY = Math.cos(idleTime * 0.8) * 3;
                }
            }

            // 应用指针旋转
            if (compassPointer) {
                compassPointer.setAttribute("transform", `rotate(${currentAngle}, 100, 100)`);
            }

            // 表盘反向视差偏转
            if (compassDial) {
                const dialAngle = -currentAngle * 0.15;
                compassDial.setAttribute("transform", `rotate(${dialAngle}, 100, 100)`);
            }

            // 应用3D倾斜
            if (compass) {
                compass.style.transform = `perspective(500px) rotateX(${currentTiltX}deg) rotateY(${currentTiltY}deg)`;
            }
        }
        requestAnimationFrame(updateCompass);
    }

    requestAnimationFrame(updateCompass);
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

            // 切换内容区域 of 显示
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
