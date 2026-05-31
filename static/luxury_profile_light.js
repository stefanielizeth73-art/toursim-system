/**
 * Luxury Profile Light-Mode Page Interactions
 * Features: Seamless Narrative Line Scroll Growth, Parallax Image sliding,
 * GSAP-like kinetic counters, and staggered element revealing.
 */
document.addEventListener("DOMContentLoaded", () => {
    initStaggeredReveal();
    initNarrativeThread();
    initParallaxTilt();
    initStatsCounter();
});

/**
 * 1. 错落分层优雅浮出 (Staggered Load Reveal)
 */
function initStaggeredReveal() {
    const reveals = document.querySelectorAll(".profile-panel, .profile-hero, .profile-content-card, .profile-food-card");
    reveals.forEach((el, index) => {
        el.style.animation = "revealUp 1.2s cubic-bezier(0.16, 1, 0.3, 1) both";
        el.style.animationDelay = `${index * 0.1}s`;
    });
}

/**
 * 2. 连续性“叙事金线”流溢生长与金珠随动 (Narrative Thread Flow Control)
 */
function initNarrativeThread() {
    const thread = document.querySelector(".narrative-line-glow");
    const bead = document.querySelector(".narrative-bead");
    const container = document.querySelector(".narrative-container");

    if (!thread || !bead || !container) return;

    // 入场自动弹射引导：前一秒金线自动优雅下探 120 像素
    setTimeout(() => {
        thread.style.height = "120px";
        bead.style.top = "120px";
    }, 400);

    function updateThread() {
        const scrollTop = window.scrollY;
        const windowHeight = window.innerHeight;
        const docHeight = document.documentElement.scrollHeight;

        // 算出当前的全局滚动比例，并在最大可用高度内进行映射
        const containerHeight = container.clientHeight;
        const scrollPercent = scrollTop / (docHeight - windowHeight);

        // 阻尼平滑高度计算（最小120px）
        let targetHeight = scrollPercent * containerHeight;
        if (targetHeight < 120) targetHeight = 120;
        if (targetHeight > containerHeight) targetHeight = containerHeight;

        thread.style.height = `${targetHeight}px`;
        bead.style.top = `${targetHeight}px`;
    }

    window.addEventListener("scroll", updateThread);
    window.addEventListener("resize", updateThread);
}

/**
 * 3. 卡片图片的弹性视差反向移位 (Kinetic Parallax Sliding Effect)
 */
function initParallaxTilt() {
    const foodCards = document.querySelectorAll(".profile-food-card");

    foodCards.forEach(card => {
        const img = card.querySelector("img");
        if (!img) return;

        card.addEventListener("mousemove", (e) => {
            const rect = card.getBoundingClientRect();
            const width = rect.width;

            // 计算鼠标在卡片上的横向百分比位置 (-0.5 到 +0.5)
            const mouseXPercent = (e.clientX - rect.left) / width - 0.5;

            // 产生极其微幅的反方向视差平移效果，高端奢侈品动效重在细微
            const shiftX = -mouseXPercent * 10; // 反方向平移最大5px
            img.style.transform = `scale(1.08) translateX(${shiftX}px)`;
        });

        card.addEventListener("mouseleave", () => {
            img.style.transform = `scale(1) translateX(0)`;
        });
    });
}

/**
 * 4. 骨瓷白高雅数据生长动画 (Stats Kinetic Counter)
 */
function initStatsCounter() {
    const statElements = document.querySelectorAll(".profile-stat-strip strong, .profile-mini-metrics strong");

    statElements.forEach(el => {
        const text = el.innerText.trim();
        const value = parseFloat(text);
        if (isNaN(value)) return;

        let start = 0;
        const duration = 1500; // 长效阻尼递增时长
        const stepTime = 20;
        const steps = duration / stepTime;
        const increment = value / steps;

        const isDecimal = text.includes('.');
        let currentStep = 0;

        const counter = setInterval(() => {
            currentStep++;
            start += increment;

            if (currentStep >= steps) {
                el.innerText = text;
                clearInterval(counter);
            } else {
                el.innerText = isDecimal ? start.toFixed(1) : Math.floor(start);
            }
        }, stepTime);
    });
}
