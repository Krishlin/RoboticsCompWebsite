/* owner: shared / lead
   The photo viewer on the past-events page. An enhancement in the strict
   sense: every photo is already a link to its largest cut, so with this file
   blocked, or in a browser without <dialog>, a click opens the picture
   itself. Here those clicks open it full-screen instead, with previous and
   next across every photo on the page, the arrow keys, and Escape to close.

   A click with a modifier key is left alone, so "open in new tab" still
   does what it says. */

(function () {
    "use strict";

    var viewer = document.getElementById("viewer");
    if (!viewer || typeof viewer.showModal !== "function") {
        return;
    }

    var img = viewer.querySelector(".viewer-img");
    var count = viewer.querySelector(".viewer-count");
    var links = Array.prototype.slice.call(document.querySelectorAll(".photo a"));
    if (!img || !count || !links.length) {
        return;
    }

    var current = 0;
    var opener = null;

    function preload(index) {
        var link = links[(index + links.length) % links.length];
        var image = new Image();
        image.sizes = "100vw";
        image.srcset = link.getAttribute("data-srcset") || "";
        image.src = link.href;
    }

    function show(index) {
        current = (index + links.length) % links.length;
        var link = links[current];
        var thumb = link.querySelector("img");

        // Width and height first, so the frame takes the photo's shape
        // before the bytes arrive rather than jumping when they do.
        if (thumb) {
            img.width = Number(thumb.getAttribute("width")) || 0;
            img.height = Number(thumb.getAttribute("height")) || 0;
            img.alt = thumb.alt;
        }
        img.sizes = "100vw";
        img.srcset = link.getAttribute("data-srcset") || "";
        img.src = link.href;
        count.textContent = (current + 1) + " of " + links.length;

        preload(current + 1);
        preload(current - 1);
    }

    links.forEach(function (link, index) {
        link.setAttribute("aria-haspopup", "dialog");
        link.addEventListener("click", function (evt) {
            if (evt.button !== 0 || evt.metaKey || evt.ctrlKey || evt.shiftKey || evt.altKey) {
                return;
            }
            evt.preventDefault();
            opener = link;
            show(index);
            viewer.showModal();
        });
    });

    viewer.addEventListener("click", function (evt) {
        var step = evt.target.closest("[data-step]");
        if (step) {
            show(current + Number(step.getAttribute("data-step")));
            return;
        }
        // The close button, or anywhere that is not the photo or the bar.
        if (evt.target.closest("[data-close]") ||
                evt.target === viewer ||
                evt.target.classList.contains("viewer-frame")) {
            viewer.close();
        }
    });

    viewer.addEventListener("keydown", function (evt) {
        if (evt.key === "ArrowRight") {
            evt.preventDefault();
            show(current + 1);
        } else if (evt.key === "ArrowLeft") {
            evt.preventDefault();
            show(current - 1);
        }
    });

    viewer.addEventListener("close", function () {
        // Stops a large download that is still running for a photo nobody
        // is looking at any more.
        img.removeAttribute("srcset");
        img.removeAttribute("src");
        if (opener) {
            opener.focus();
        }
    });
})();
