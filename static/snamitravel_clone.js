document.addEventListener('DOMContentLoaded', () => {
    const body = document.body;
    const header = document.querySelector('[data-site-header]');
    const hamburger = document.querySelector('.snami-hamburger');
    const menuOverlay = document.querySelector('.snami-menu-overlay');
    const loginModal = document.getElementById('login-modal');
    const registerModal = document.getElementById('register-modal');
    const openLoginButtons = document.querySelectorAll('.js-open-login');
    const openRegisterButtons = document.querySelectorAll('.js-open-register');
    const closeButtons = document.querySelectorAll('.js-close-modal');
    const heroVideo = document.querySelector('.snami-hero-bg[data-hls-src]');
    const magneticWraps = document.querySelectorAll('.snami-btn-capsule-container');
    const revealItems = document.querySelectorAll('.reveal-line, .reveal-title, .reveal-pop');
    const parallaxImages = document.querySelectorAll('.js-parallax-img');

    const initializeHeroVideo = () => {
        if (!heroVideo) return;

        const hlsSource = heroVideo.dataset.hlsSrc;
        if (!hlsSource) return;

        if (heroVideo.canPlayType('application/vnd.apple.mpegurl')) {
            heroVideo.src = hlsSource;
        } else if (window.Hls?.isSupported()) {
            const hls = new window.Hls({
                enableWorker: true,
                lowLatencyMode: false,
            });
            hls.loadSource(hlsSource);
            hls.attachMedia(heroVideo);
        }

        const playHeroVideo = () => {
            heroVideo.play().catch(() => {
                // Muted autoplay can still be deferred by some browsers; poster remains as fallback.
            });
        };

        heroVideo.addEventListener('canplay', playHeroVideo, { once: true });
        playHeroVideo();
    };

    initializeHeroVideo();

    const setHeaderState = () => {
        if (!header) return;
        header.classList.toggle('scrolled', window.scrollY > 24);
    };

    setHeaderState();
    window.addEventListener('scroll', setHeaderState, { passive: true });

    const setBodyLock = () => {
        const menuOpen = menuOverlay?.classList.contains('active');
        const modalOpen = document.querySelector('.snami-modal-overlay.active');
        body.classList.toggle('snami-lock', Boolean(menuOpen || modalOpen));
    };

    const closeMenu = () => {
        if (!hamburger || !menuOverlay) return;
        hamburger.classList.remove('active');
        hamburger.setAttribute('aria-expanded', 'false');
        menuOverlay.classList.remove('active');
        menuOverlay.setAttribute('aria-hidden', 'true');
        header?.classList.remove('menu-open');
        setBodyLock();
    };

    const toggleMenu = () => {
        if (!hamburger || !menuOverlay) return;
        const isOpen = hamburger.classList.toggle('active');
        hamburger.setAttribute('aria-expanded', String(isOpen));
        menuOverlay.classList.toggle('active', isOpen);
        menuOverlay.setAttribute('aria-hidden', String(!isOpen));
        header?.classList.toggle('menu-open', isOpen);
        setBodyLock();
    };

    hamburger?.addEventListener('click', toggleMenu);
    menuOverlay?.querySelectorAll('a').forEach((link) => {
        link.addEventListener('click', closeMenu);
    });

    const closeModal = (modal) => {
        if (!modal) return;
        modal.classList.remove('active');
        modal.setAttribute('aria-hidden', 'true');
        setBodyLock();
    };

    const closeAllModals = () => {
        closeModal(loginModal);
        closeModal(registerModal);
    };

    const openModal = (modal) => {
        if (!modal) return;
        closeMenu();
        closeAllModals();
        modal.classList.add('active');
        modal.setAttribute('aria-hidden', 'false');
        const firstInput = modal.querySelector('input, button, a');
        window.setTimeout(() => firstInput?.focus({ preventScroll: true }), 80);
        setBodyLock();
    };

    openLoginButtons.forEach((button) => {
        button.addEventListener('click', (event) => {
            event.preventDefault();
            openModal(loginModal);
        });
    });

    openRegisterButtons.forEach((button) => {
        button.addEventListener('click', (event) => {
            event.preventDefault();
            openModal(registerModal);
        });
    });

    closeButtons.forEach((button) => {
        button.addEventListener('click', () => closeModal(button.closest('.snami-modal-overlay')));
    });

    [loginModal, registerModal].forEach((modal) => {
        modal?.addEventListener('click', (event) => {
            if (event.target === modal) {
                closeModal(modal);
            }
        });
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            closeMenu();
            closeAllModals();
        }
    });

    if (loginModal?.querySelector('.snami-flash-message')) {
        openModal(loginModal);
    }

    if (window.location.hash === '#login') {
        openModal(loginModal);
    }

    if (window.location.hash === '#register') {
        openModal(registerModal);
    }

    magneticWraps.forEach((wrap) => {
        const button = wrap.querySelector('.snami-btn-capsule');
        if (!button) return;

        wrap.addEventListener('pointermove', (event) => {
            const rect = wrap.getBoundingClientRect();
            const x = event.clientX - rect.left - rect.width / 2;
            const y = event.clientY - rect.top - rect.height / 2;
            button.style.transform = `translate(${x * 0.18}px, ${y * 0.18}px) scale(1.03)`;
        });

        wrap.addEventListener('pointerleave', () => {
            button.style.transform = '';
        });
    });

    const originSection = document.querySelector('.snami-origin');
    const originMedia = originSection?.querySelector('.snami-origin-media');
    const originCopy = originSection?.querySelector('.snami-origin-copy');
    let animationFrame = 0;

    const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));
    const easeOutQuart = (value) => 1 - Math.pow(1 - clamp(value), 4);
    const smoothStep = (value) => {
        const progress = clamp(value);
        return progress * progress * progress * (progress * ((progress * 6) - 15) + 10);
    };

    const setupGentleScrollDamping = () => {
        const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
        const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
        if (reduceMotion.matches || !finePointer.matches) return;

        let targetY = window.scrollY;
        let currentY = window.scrollY;
        let scrollFrame = 0;

        const maxScrollY = () => Math.max(0, document.documentElement.scrollHeight - window.innerHeight);

        const stopDamping = () => {
            if (scrollFrame) {
                window.cancelAnimationFrame(scrollFrame);
                scrollFrame = 0;
            }
            targetY = window.scrollY;
            currentY = targetY;
        };

        const animateScroll = () => {
            currentY += (targetY - currentY) * 0.18;

            if (Math.abs(targetY - currentY) < 0.6) {
                currentY = targetY;
                window.scrollTo(0, targetY);
                scrollFrame = 0;
                return;
            }

            window.scrollTo(0, currentY);
            scrollFrame = window.requestAnimationFrame(animateScroll);
        };

        window.addEventListener('wheel', (event) => {
            if (event.defaultPrevented || event.ctrlKey || event.metaKey || body.classList.contains('snami-lock')) return;

            event.preventDefault();
            currentY = window.scrollY;

            const wheelDelta = event.deltaMode === 1
                ? event.deltaY * 16
                : event.deltaMode === 2
                    ? event.deltaY * window.innerHeight
                    : event.deltaY;

            targetY = clamp(targetY + (wheelDelta * 0.92), 0, maxScrollY());

            if (!scrollFrame) {
                scrollFrame = window.requestAnimationFrame(animateScroll);
            }
        }, { passive: false });

        window.addEventListener('keydown', stopDamping, { passive: true });
        window.addEventListener('scroll', () => {
            if (!scrollFrame) {
                targetY = window.scrollY;
                currentY = targetY;
            }
        }, { passive: true });
    };

    setupGentleScrollDamping();

    const revealElement = (element, viewportHeight) => {
        if (element.closest('.snami-hero') || element.closest('.snami-origin')) return;

        const rect = element.getBoundingClientRect();
        const rawProgress = (viewportHeight * 0.9 - rect.top) / (viewportHeight * 0.48);
        const progress = easeOutQuart(rawProgress);
        const isPop = element.classList.contains('reveal-pop');
        const isTitle = element.classList.contains('reveal-title');
        const distance = isTitle ? 70 : isPop ? 60 : 54;
        const scale = isPop ? 0.96 + (0.04 * progress) : 1;

        element.style.opacity = String(progress);
        element.style.transform = `translateY(${distance * (1 - progress)}px) scale(${scale})`;
    };

    const updateAnimations = () => {
        const viewportHeight = window.innerHeight;

        if (originSection && originMedia) {
            const rect = originSection.getBoundingClientRect();
            const rawProgress = (viewportHeight - rect.top) / (viewportHeight * 0.92);
            const progress = smoothStep(rawProgress);
            originSection.style.setProperty('--origin-progress', progress.toFixed(4));

            if (originCopy) {
                originCopy.style.pointerEvents = progress > 0.55 ? 'auto' : 'none';
            }
        }

        parallaxImages.forEach((image) => {
            const rect = image.getBoundingClientRect();
            if (rect.bottom < 0 || rect.top > viewportHeight) return;
            const progress = (rect.top + rect.height / 2 - viewportHeight / 2) / viewportHeight;
            image.style.transform = `translateY(${progress * -34}px) scale(1.055)`;
        });

        revealItems.forEach((item) => revealElement(item, viewportHeight));
        animationFrame = 0;
    };

    const requestAnimationUpdate = () => {
        if (animationFrame) return;
        animationFrame = window.requestAnimationFrame(updateAnimations);
    };

    window.addEventListener('scroll', requestAnimationUpdate, { passive: true });
    window.addEventListener('resize', requestAnimationUpdate);
    updateAnimations();
});
