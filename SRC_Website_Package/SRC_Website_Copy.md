# SRC Website Copy

Final copy for the competitor-facing SRC website. Everything below is ready to paste. Text in [brackets] is a link target or a value to be filled in by SRC.

## Assets (in the images folder)

| File | Where it goes | Alt text |
|---|---|---|
| summit_logo_transparent.png | Navigation logo, footer, hero on any non-white background | Summit |
| summit_logo_on_white.png | Hero on the Home page (white background) | Summit |
| summit_hill_named.png | Home page "The Hill" section; Summit page "The Hill" section | The Hill, top and side view, with the five zones named |
| summit_hill_field_spec.png | Summit page, Resources, "Field specification" | Dimensioned drawing of the Hill with zone radii and colors |
| kit_bot.png | Kit page, left image | The assembled kit robot |
| kit_parts.png | Kit page, right image | The parts included in the kit |
| summit-manual-v1.0.pdf | Served at /summit/manual | |

All PNGs have transparent backgrounds except summit_logo_on_white.png. The wordmark is light cyan, so use the transparent version only on dark or colored backgrounds and the on-white version on white.

---

## Navigation (all pages)

Logo: summit_logo_transparent.png (or summit_logo_on_white.png on a white bar). Links to Home.

Menu, left to right:
- Home
- About
- Summit
- Events
- Kit
- Contact

Button at the right of the navigation bar: **Register** → /register

---

## Footer (all pages)

STEMsters Robotics Competition
A program of STEMsters, a student-led 501(c)(3) nonprofit organization

Links: Game Manual · Register · Kit · Contact
Email: [src email]
Instagram: [handle]

Climb together.

---

## Home — /

**Hero**

Image: summit_logo_on_white.png, large.

Subline: The STEMsters Robotics Competition. An autonomous robotics competition for middle and high school teams in Southern California.

Buttons: **Register a team** → /register · **Game manual** → /summit/manual · **October 24 event** → /events/october-24-2026

**Section: The game**

Heading: Summit

Summit is the SRC game for 2026. Two autonomous robots, one red and one blue, compete on a small raised hill. A robot wins by pushing its opponent off the Hill, or by being higher on the Hill when time expires.

- Robots must fit within 10 cm by 10 cm at the start of the match, weigh 500 g or less, and be controlled by a micro:bit. There is no height limit, and every other part is the team's choice.
- Matches last three minutes. A referee's field controller starts and stops both robots by radio.
- Teams consist of one to four students and one adult who is present for the entire event.
- Events consist of qualification matches followed by a single-elimination bracket.

Button: **Learn the game** → /summit

**Section: The Hill**

Image: summit_hill_named.png

The Hill is a 3D-printed PLA mound, 42 cm in diameter. Each ring is a different color so that a color sensor can identify where the robot is. Full dimensions and print files are available on the Summit page.

**Section: Cost**

Heading: Under $150

Registration is $20 per team. The optional kit is $100 and is a complete, competition-legal robot. Teams may compete with the kit, with a robot of their own design, or with a combination of the two. Apart from the micro:bit, every part is the team's choice.

Buttons: **View the kit** → /kit · **Register** → /register

**Section: Next event**

Heading: October 24, 2026

Arcadia, California. Check-in opens at 9:00 AM, matches begin at 10:00 AM, and awards are presented at 2:15 PM. Registration is open.

Buttons: **Event details** → /events/october-24-2026 · **Register** → /register

**Section: Climb together**

Climb together is the SRC conduct rule. Teams compete hard, help other teams when they need it, respect the referees and volunteers, and treat a win and a loss the same way. The rule applies to students and adults alike.

---

## About — /about

**Heading:** About SRC

The STEMsters Robotics Competition (SRC) is an autonomous robotics competition for middle and high school students in Southern California. It is organized by STEMsters, a student-led 501(c)(3) nonprofit that provides hands-on STEM education to elementary and middle school students through high school volunteers.

**Subheading:** Why SRC exists

Most robotics competitions cost several hundred dollars per team before the first match is played, and that cost determines who is able to participate. SRC was designed to remove that barrier. The robot is small, the kit is optional, the rulebook is nine pages, and every part other than the micro:bit is the team's choice. A team's total cost, including the robot and registration, is under $150.

**Subheading:** Who runs it

SRC is designed, organized, and refereed by STEMsters volunteers who are themselves high school students. The game, the field, the kit, and the field controller were all developed by students.

**Subheading:** Climb together

Climb together is the SRC conduct rule. Teams compete hard, help other teams when they need it, respect the referees and volunteers, and treat a win and a loss the same way. The rule applies to students and adults alike.

Buttons: **Register** → /register · **Contact** → /contact

---

## Summit — /summit

**Heading:** Summit

Summit is the SRC game for 2026. It is a sumo match between two autonomous robots on the Hill. A robot wins by pushing its opponent off the Hill, or by being higher on the Hill when the match ends. Robots run entirely on their own code. Once a match begins, no one may touch or control them.

Button: **Game manual (PDF)** → /summit/manual

**Section: The Hill**

Image: summit_hill_named.png

- **Plateau (white).** The flat top of the Hill, 2 cm above the base.
- **Inner Slope (green) and Outer Slope (yellow).** The two sloped rings between the Plateau and the base.
- **Flat Band (red and blue).** The flat base. The red robot starts on the red half and the blue robot on the blue half.
- **Edge Band (black).** The outermost ring. Its outer edge is the boundary of the Hill.

**Section: Rules summary**

- Robots must fit within a 10 cm by 10 cm footprint at the start of the match and weigh 500 g or less. There is no height limit. After the start signal, robots may expand without restriction.
- A micro:bit running the team's own code must control the robot. All other parts are the team's choice.
- Matches last three minutes. The referee's field controller starts and stops both robots by radio.
- A ring-out ends the match. If time expires, the robot in the higher zone wins.
- Teams consist of one to four students and one adult.

The complete rules are in the game manual. It is nine pages long.

Button: **Game manual (PDF)** → /summit/manual

**Section: Resources**

- **Starter code** → [MakeCode share link]. Includes the official field-controller start/stop code. Enter your team number once; no other changes are required.
- **Kit build guide** → [build guide link]
- **Field print files** → [print files link]. CAD and STL files for the Hill.
- **Field specification** → summit_hill_field_spec.png. The dimensioned drawing and zone table, identical to Appendix A of the manual.
- **Filament list** → [filament list link]. The exact filament used for each zone, so that a practice field reads the same as the competition field.
- **Reference sensor readings** → [readings link]. Readings taken with the kit color sensor at the kit's mounting height. These are a starting point only; calibrate on a real field.

**Section: Practice fields**

Official practice fields are printed from the same filament as the competition fields. Order one with your registration, or download the print files and produce your own.

Button: **Order a practice field** → /register

---

## Game manual — /summit/manual

A permanent address that always serves the current version of the manual as a PDF. This page has no content of its own. When a new version is released, the file at this address is replaced and the version number is posted on the Summit page.

---

## Events — /events

**Heading:** Events

**Card: October 24, 2026**

Arcadia, California. Registration is open.

Buttons: **Event details** → /events/october-24-2026 · **Register** → /register

Below the card: One event is scheduled this season. Each event is governed by the version of the game manual released before it.

---

## Event page — /events/october-24-2026

**Heading:** Summit, October 24, 2026

Saturday, October 24, 2026. The gymnasium at Arcadia High School, Arcadia, California. Parking and entrance information will be emailed to registered teams the week before the event.

Buttons: **Register** → /register · **Registered teams** → /events/october-24-2026/teams · **Results** → /events/october-24-2026/results

**Schedule**

8:00 AM. Volunteers arrive and set up. The gym is closed to teams until setup is complete.

9:00 AM. Check-in opens. Both Hills are open for sensor calibration on the actual fields under the actual lighting. Inspection opens at the same time and may be repeated as many times as necessary.

9:50 AM. Team meeting at the field. Ten minutes covering the schedule, the Climb together rule, and questions.

10:00 AM. Qualification matches begin. Every team plays the same number of matches against randomly assigned opponents. The number is determined by the team count and posted with the schedule. Excellence judges visit team tables during qualification matches for a short interview.

11:30 AM. Inspection and calibration close. A robot that has not passed inspection forfeits its matches until it passes.

11:45 AM. Lunch. The bracket is posted at 12:00 PM.

12:30 PM. Bracket matches begin. Single elimination, seeded from qualification. Each pairing is first to two wins.

2:15 PM. Awards.

2:30 PM. Teardown. Teams clear their tables. The gym must be empty by 3:00 PM.

**Awards**

Every award winner receives a trophy. The Champion also receives the Summit banner. There are no cash prizes.

- **Champion.** The bracket winner, middle school or high school.
- **Middle School Champion.** The middle school team that advanced furthest in the bracket, with ties broken by qualification rank. If a middle school team wins the Championship, this award goes to the next highest-placing middle school team.
- **Excellence, Middle School** and **Excellence, High School.** Awarded at each level to the team that best explains how it designed, tested, and improved its robot, and how it supported other teams. Judged by a short interview at the team's table during qualification matches. No written submission is required.
- **Sportsmanship.** Awarded to the team that best demonstrates the Climb together rule throughout the event.

**Exhibition field**

A second Hill runs king-of-the-hill matches throughout the afternoon. The winner stays on the field and faces the next challenger. Open to any robot that has passed inspection, including teams eliminated from the bracket. Exhibition results do not affect rankings, the bracket, or awards.

**Areas**

Team area: rostered students and the team's adult only. Spectator area: open to everyone. Field: the two handlers and the referees.

**What to bring**

- Your robot, with the official start/stop code loaded and your team number entered
- A laptop with MakeCode and a USB cable
- Your charger
- A completed consent and release form for each student
- Your team's adult

Button: **Register** → /register

---

## Registered teams — /events/october-24-2026/teams

**Heading:** Registered teams, October 24, 2026

Table, one row per team, sorted by team number:

| Team | Name | Level | School or independent | Roster |

The roster column shows first name and last initial only.

Below the table: Teams are listed once payment has cleared. The list is updated within one business day.

Button: **Register** → /register

---

## Results — /events/october-24-2026/results

**Heading:** Results, October 24, 2026

Before the event: Qualification rankings and the bracket will be posted here during the event on October 24.

During the event: embed or link the live bracket from the tournament software.

After the event: the final bracket, qualification rankings, and award winners.

---

## Register — /register

**Heading:** Register for Summit, October 24, 2026

Registration is $20 per team and covers the competition fields and awards. Your team number is emailed to you immediately after registration.

**Section: Team**
- Team name (text)
- School, or "Independent" (text)

**Section: Roster**

One to four students. Full names are kept private. The website displays first name and last initial only.

For each student, up to four:
- First name (text)
- Last name (text)
- Grade in the 2026-27 school year (dropdown: 6, 7, 8, 9, 10, 11, 12)

Note: A team with any student in grades 9 through 12 competes as a high school team.

**Section: Adult**

Each team must register a coach or supervising adult, 18 or older, who is present for the entire event.
- Full name (text)
- Email (email)
- Phone (phone)

**Section: Add-ons**
- [ ] Official kit, $100 (all parts except the micro:bit)
- [ ] micro:bit, $20
- [ ] Practice field, [$ price]

Note: Kits and practice fields are picked up at [pickup location] or at the event. You will be notified by email when your order is ready.

**Section: Agreements**
- [ ] I have read the Summit game manual. (link: /summit/manual)
- [ ] Our team agrees to follow the Climb together rule.
- [ ] I consent to the team name and roster (first name and last initial) being listed on the SRC website.

**Payment**

Line items: Registration, $20, plus any add-ons selected. Total.

Button: **Pay and register**

**Confirmation page**

Heading: Registration complete

Your team number has been sent to [adult email]. Before the event, read the game manual, load the starter code and enter your team number, and obtain a signed consent and release form for each student.

Buttons: **Game manual** → /summit/manual · **Consent and release form** → [form link] · **Summit resources** → /summit

**Confirmation email**

Subject: Team [number], registered for Summit

Body:

[Team name] is registered for Summit on October 24, 2026. Your team number is [number]. Enter it in the official start/stop code so that the field controller can address your robot.

Before the event:

1. Read the game manual: [manual link]
2. Load the starter code and enter your team number: [MakeCode link]
3. Obtain a signed consent and release form for each student: [form link]. Bring the forms to check-in if they are not submitted online.

Event details, schedule, and what to bring: [event page link]

Questions: [src email]

STEMsters Robotics Competition

---

## Kit — /kit

**Heading:** The official kit

Images: kit_bot.png and kit_parts.png, side by side.

The kit is optional. It is a complete, competition-legal robot. Teams may build it and compete with it as is, or use it as the starting point for their own design. It is programmed in MakeCode.

**Included**
- ELECFREAKS Wukong expansion board with built-in battery
- Two Geekservo 2 kg 360-degree continuous-rotation motors
- HC-SR04 ultrasonic sensor for detecting the opponent
- TCS34725 color sensor for reading the zone
- LEGO Technic chassis parts and wheels
- Motor cables
- Starter code, including the official field-controller start/stop code

**Not included**
- A micro:bit. Add one for $20 at registration, or use one you already have.
- A laptop and a USB cable.
- A small screwdriver.

**Pricing**

Kit: $100
micro:bit: $20
Practice field: [$ price]

Kits are ordered on the registration form and picked up at [pickup location] or at the event.

Buttons: **Register and order** → /register · **Build guide** → [build guide link] · **Starter code** → [MakeCode link]

---

## Contact — /contact

**Heading:** Contact

For questions about the rules, registration, the kit, or the event, email [src email].

We respond within two business days. Rule questions that apply to all teams are added to the next version of the game manual.

Instagram: [handle]

STEMsters Robotics Competition
A program of STEMsters, a student-led 501(c)(3) nonprofit organization
