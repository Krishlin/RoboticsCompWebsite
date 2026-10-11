/* owner: shared / lead
   Two small enhancements to the landing page. Both are enhancements in the
   strict sense: the page is usable with this file blocked, and everything
   here only takes something away from that baseline once it is running.

   The Hill in the hero is a separate file, js/hill.js. */

(function () {
    "use strict";

    /* -----------------------------------------------------------------
       Nav. The section links are a plain visible list in the HTML, which
       is what a visitor without JavaScript keeps. Here they are collapsed
       behind the Menu button instead — the button ships hidden precisely
       so that it never appears without something to operate it.
       ----------------------------------------------------------------- */

    var nav = document.getElementById("site-nav");
    var toggle = document.getElementById("nav-toggle");
    var links = document.getElementById("nav-links");

    if (nav && toggle && links) {
        // Below this the bar has no room for five links and a button, and
        // it matches the breakpoint the stylesheet collapses the nav at.
        var narrow = window.matchMedia("(max-width: 880px)");

        function setOpen(open) {
            nav.classList.toggle("is-open", open);
            toggle.setAttribute("aria-expanded", open ? "true" : "false");
        }

        function sync() {
            // On a wide screen the list is always shown, so the button would
            // be claiming to control something it does not.
            toggle.hidden = !narrow.matches;
            setOpen(!narrow.matches);
        }

        nav.classList.add("nav-has-js");
        toggle.removeAttribute("hidden");
        sync();

        // Chrome and Safari disagreed about addListener for years; both have
        // supported addEventListener on a MediaQueryList since 2020, and the
        // guard keeps an older browser on the visible-list fallback rather
        // than throwing on load.
        if (narrow.addEventListener) {
            narrow.addEventListener("change", sync);
        }

        toggle.addEventListener("click", function () {
            setOpen(toggle.getAttribute("aria-expanded") !== "true");
        });

        // A same-page link does not reload, so the panel would otherwise stay
        // open over the section it just moved to.
        links.addEventListener("click", function (evt) {
            if (evt.target.closest("a") && narrow.matches) {
                setOpen(false);
            }
        });

        document.addEventListener("keydown", function (evt) {
            if (evt.key === "Escape" && nav.classList.contains("is-open") && narrow.matches) {
                setOpen(false);
                toggle.focus();
            }
        });
    }

    /* -----------------------------------------------------------------
       Kit robot gallery. The stage is a scroll-snap row and the rail is a
       list of in-page links into it, so swiping and tapping both already
       work. What is missing without script is any sign of which view you
       are on, and the fact that following a link into a horizontal
       scroller also drags the page up to it. Both are fixed here.
       ----------------------------------------------------------------- */

    var stage = document.getElementById("bot-stage");
    var rail = document.querySelector(".bot-rail");

    if (!stage || !rail) {
        return;
    }

    var thumbs = Array.prototype.slice.call(rail.querySelectorAll(".bot-thumb"));

    function mark(id) {
        thumbs.forEach(function (thumb) {
            var current = thumb.dataset.slide === id;
            thumb.classList.toggle("is-current", current);
            // aria-current rather than aria-selected: these are links into
            // the page, not tabs, whatever they look like.
            if (current) {
                thumb.setAttribute("aria-current", "true");
            } else {
                thumb.removeAttribute("aria-current");
            }
        });
    }

    thumbs.forEach(function (thumb) {
        thumb.addEventListener("click", function (evt) {
            var slide = document.getElementById(thumb.dataset.slide);
            if (!slide) {
                return; // Let the browser follow the href and do its best.
            }
            evt.preventDefault();
            // inline: centre moves the stage; block: nearest stops it
            // yanking the whole page up to the gallery to do so.
            slide.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
            mark(thumb.dataset.slide);
        });
    });

    if ("IntersectionObserver" in window) {
        var watcher = new IntersectionObserver(
            function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        mark(entry.target.id);
                    }
                });
            },
            // Against the stage itself, and a majority threshold, so the
            // reading changes once per swipe rather than twice.
            { root: stage, threshold: 0.6 }
        );
        Array.prototype.forEach.call(stage.children, function (slide) {
            watcher.observe(slide);
        });
    } else if (thumbs.length) {
        mark(thumbs[0].dataset.slide);
    }
})();
