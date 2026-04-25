// Auto-close flash messages after 5 seconds (fallback for non-Alpine pages)
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-auto-close]').forEach(function (el) {
        setTimeout(function () {
            el.style.transition = 'opacity 0.3s ease';
            el.style.opacity = '0';
            setTimeout(function () { el.remove(); }, 300);
        }, 5000);
    });
});

// Scroll Reveal — semua varian dengan stagger delay
document.addEventListener('DOMContentLoaded', function () {
    var selectors = '.scroll-reveal, .scroll-reveal-left, .scroll-reveal-right, .scroll-reveal-scale';
    var reveals = document.querySelectorAll(selectors);
    if (reveals.length === 0) return;

    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry, index) {
            if (entry.isIntersecting) {
                setTimeout(function () {
                    entry.target.classList.add('revealed');
                }, index * 80);
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.12 });

    reveals.forEach(function (el) { observer.observe(el); });
});

// Counter Animation — angka naik dari 0 ke target
document.addEventListener('DOMContentLoaded', function () {
    var counters = document.querySelectorAll('.counter-animate');
    if (counters.length === 0) return;

    var counterObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                var el = entry.target;
                var target = parseInt(el.textContent, 10);
                if (isNaN(target) || target === 0) return;
                var current = 0;
                var step = Math.ceil(target / 40);
                var timer = setInterval(function () {
                    current += step;
                    if (current >= target) {
                        current = target;
                        clearInterval(timer);
                    }
                    el.textContent = current;
                }, 30);
                counterObserver.unobserve(el);
            }
        });
    }, { threshold: 0.3 });

    counters.forEach(function (el) { counterObserver.observe(el); });
});
