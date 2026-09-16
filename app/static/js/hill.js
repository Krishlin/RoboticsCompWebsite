/* owner: shared / lead
   The draggable Hill in the landing-page hero.

   Geometry is the real field, in SVG units of 1 mm: the Hill is 420 across
   because it is 42 cm across. Zone radii come from Appendix A of the game
   manual (summit_hill_field_spec.png), so this reads the same as the field a
   team will actually compete on.

   The readout reports what the robot's colour sensor sees. On the real robot
   that sensor is mounted under the middle of the chassis, so the zone is
   decided by the robot's centre point, not by its footprint. */

(function () {
    "use strict";

    var stage = document.getElementById("hill-stage");
    var svg = document.getElementById("hill-svg");
    var robot = document.getElementById("robot");
    if (!stage || !svg || !robot) {
        return; // Page rendered without the hero figure; nothing to wire up.
    }

    var swatchEl = document.getElementById("readout-swatch");
    var zoneEl = document.getElementById("readout-zone");
    var detailEl = document.getElementById("readout-detail");

    var CENTER = 210;
    var OFF_HILL = 210; // outer edge of the Edge Band: past this is a ring-out
    var MAX_DRAG = 238; // let the robot leave the Hill, but not the viewBox

    // Outer radius of each zone, innermost first. Matched in order, so the
    // first entry whose radius contains the sensor wins.
    var ZONES = [
        {
            r: 50,
            name: "Zone 1  Plateau",
            color: "#f0f0f0",
            detail: "The sensor reads white. 2.0 cm up — the highest zone on the Hill, and exactly one robot wide."
        },
        {
            r: 80,
            name: "Zone 2  Inner Slope",
            color: "#4fae55",
            detail: "The sensor reads green. Climbing, 1 cm below the Plateau."
        },
        {
            r: 110,
            name: "Zone 3  Outer Slope",
            color: "#e5c32c",
            detail: "The sensor reads yellow. Climbing, 2 cm below the Plateau."
        },
        {
            r: 180,
            name: "Zone 4  Flat Band",
            color: null, // red or blue, decided by which half the robot is on
            detail: null
        },
        {
            r: 210,
            name: "Zone 5  Edge Band",
            color: "#141414",
            detail: "The sensor reads black. One ring from the drop."
        }
    ];

    var RING_OUT = {
        name: "Off the Hill",
        color: "#7a1f1a",
        detail: "Ring out. The match is over and the other robot wins, however much time is left."
    };

    function readSensor(x, y) {
        var dx = x - CENTER;
        var dy = y - CENTER;
        var dist = Math.sqrt(dx * dx + dy * dy);

        if (dist > OFF_HILL) {
            return RING_OUT;
        }

        for (var i = 0; i < ZONES.length; i++) {
            if (dist <= ZONES[i].r) {
                var zone = ZONES[i];
                if (zone.color !== null) {
                    return zone;
                }
                // Flat Band: the left half is the red start, the right blue.
                return x < CENTER
                    ? {
                          name: zone.name,
                          color: "#c0433b",
                          detail: "The sensor reads red. Ground level, and where the red robot starts."
                      }
                    : {
                          name: zone.name,
                          color: "#4470d2",
                          detail: "The sensor reads blue. Ground level, and where the blue robot starts."
                      };
            }
        }
        return RING_OUT;
    }

    var START = { x: CENTER + 145, y: CENTER + 30 }; // the blue half of the Flat Band
    var pos = { x: START.x, y: START.y };

    function render() {
        robot.setAttribute("transform", "translate(" + pos.x + " " + pos.y + ")");

        var reading = readSensor(pos.x, pos.y);
        swatchEl.style.backgroundColor = reading.color;
        zoneEl.textContent = reading.name;
        detailEl.textContent = reading.detail;
        stage.classList.toggle("is-out", reading === RING_OUT);

        // Keep the slider semantics honest for assistive tech.
        robot.setAttribute("aria-label", "Robot on " + reading.name + ". " + reading.detail);
    }

    /* Pointer position in SVG user units. getScreenCTM accounts for the
       element's current size, so this stays correct at any breakpoint and
       after a resize without us listening for one. */
    function toSvgPoint(evt) {
        var ctm = svg.getScreenCTM();
        if (!ctm) {
            return null;
        }
        var point = svg.createSVGPoint();
        point.x = evt.clientX;
        point.y = evt.clientY;
        return point.matrixTransform(ctm.inverse());
    }

    function moveTo(x, y) {
        var dx = x - CENTER;
        var dy = y - CENTER;
        var dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > MAX_DRAG) {
            // Hold the robot at arm's length rather than letting it escape.
            var scale = MAX_DRAG / dist;
            x = CENTER + dx * scale;
            y = CENTER + dy * scale;
        }
        pos.x = x;
        pos.y = y;
        render();
    }

    var dragging = false;

    stage.addEventListener("pointerdown", function (evt) {
        var p = toSvgPoint(evt);
        if (!p) {
            return;
        }
        dragging = true;
        cancelDemo();
        stage.setPointerCapture(evt.pointerId);
        moveTo(p.x, p.y);
        evt.preventDefault();
    });

    stage.addEventListener("pointermove", function (evt) {
        if (!dragging) {
            return;
        }
        var p = toSvgPoint(evt);
        if (p) {
            moveTo(p.x, p.y);
        }
    });

    function endDrag(evt) {
        if (!dragging) {
            return;
        }
        dragging = false;
        if (stage.hasPointerCapture && stage.hasPointerCapture(evt.pointerId)) {
            stage.releasePointerCapture(evt.pointerId);
        }
    }

    stage.addEventListener("pointerup", endDrag);
    stage.addEventListener("pointercancel", endDrag);

    // Keyboard: the robot is focusable, so arrow keys drive it 5 mm a press.
    var KEYS = {
        ArrowUp: [0, -5],
        ArrowDown: [0, 5],
        ArrowLeft: [-5, 0],
        ArrowRight: [5, 0]
    };

    robot.addEventListener("keydown", function (evt) {
        var delta = KEYS[evt.key];
        if (!delta) {
            return;
        }
        cancelDemo();
        moveTo(pos.x + delta[0], pos.y + delta[1]);
        evt.preventDefault();
    });

    /* One orchestrated moment: on load the robot drives itself up the Hill
       once, so a visitor sees that the readout changes before touching
       anything. It stops the instant they take over, and never runs for
       someone who has asked for reduced motion. */
    var demoFrame = null;

    function cancelDemo() {
        if (demoFrame !== null) {
            cancelAnimationFrame(demoFrame);
            demoFrame = null;
        }
    }

    function runDemo() {
        var start = null;
        var DURATION = 2400;
        var from = { x: START.x, y: START.y };
        var to = { x: CENTER, y: CENTER };

        function step(now) {
            if (start === null) {
                start = now;
            }
            var t = Math.min((now - start) / DURATION, 1);
            var eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
            pos.x = from.x + (to.x - from.x) * eased;
            pos.y = from.y + (to.y - from.y) * eased;
            render();
            if (t < 1) {
                demoFrame = requestAnimationFrame(step);
            } else {
                demoFrame = null;
            }
        }
        demoFrame = requestAnimationFrame(step);
    }

    render();

    var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduced) {
        // Hold a beat so the demo reads as a deliberate move, not a glitch.
        window.setTimeout(runDemo, 700);
    }
})();
