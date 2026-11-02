# owner: shared / lead
# Every SRC event that has already happened, newest first. /past-events shows
# a card for each in this order and /past-events/<slug> is each one's recap;
# the landing page shows the first entry's results.
#
# Adding an event is two steps:
#   1. Add an entry here: the facts, the podium, and the photos picked for it.
#   2. Run tools/cut_event_photos.py against the folder the photos were
#      downloaded to. It writes the web-sized copies and the manifest the
#      route joins these entries to.
#
# A photo listed here but not yet cut is skipped rather than shown broken, so
# step 1 can land before step 2. tests/test_past_events.py fails if a listed
# photo has no cut, so it cannot ship that way by accident.
#
# Photos are named by their source filename. That is all the build tool needs
# to find them, and it keeps the picks and the words about each picture in one
# place. The alt text says what is in the frame for someone who cannot see it;
# it uses names only for the podium, which SRC announced publicly, and never
# guesses at anyone's pronouns.
#
# Plain data, no Flask import: tools/cut_event_photos.py imports this too.

PAST_EVENTS = [
    {
        "slug": "summit-2026",
        "name": "Summit 2026",
        "date": "Saturday, October 24, 2026",
        "date_short": "Sat, Oct 24, 2026",
        "venue": "Arcadia High School",
        "game": "Summit, robot king of the hill",
        "grades": "Grades 6–12",  # noqa: RUF001  (an en dash is the right mark for a range)
        # Left to right in the champions photo, which is also the order the
        # podium steps sit under it. Keep the two in step if either changes.
        # `art` is optional: a picture of the prize, as a path under
        # app/static/img, shown beside it in the prize list.
        "podium": [
            {
                "place": "1st",
                "name": "Advaith Sai Pragasthya Atluri",
                "grade": "8th grade",
                "prize": "Bambu Lab A1 3D printer",
                "art": "prize_bambu_a1_trim.png",
            },
            {
                "place": "2nd",
                "name": "May Sun",
                "grade": "7th grade",
                "prize": "4 months of ChatGPT Plus",
                "art": "prize_chatgpt.svg",
            },
            {
                "place": "3rd",
                "name": "Aden Wong",
                "grade": "8th grade",
                "prize": "4 months of Discord Nitro",
                "art": "prize_discord.svg",
            },
        ],
        # The picture on this event's card in the past-events picker: the
        # `src` of a photo listed below, so it is already cut. Optional; the
        # card falls back to the champions photo.
        "cover": "3CA03C13-F7DE-4F8E-98D6-4466BE0C0DBD.jpg",
        # The crop is (left, top, right, bottom) as fractions of the source.
        # It trims the empty chair on the right and centres each winner in a
        # third of the frame, so each podium step lands under its own person.
        "champions_photo": {
            "src": "872908613_2359458868241316_3338420712098953962_n.jpg",
            "crop": (0.039, 0.0, 0.884, 1.0),
            "alt": "Advaith Sai Pragasthya Atluri, May Sun and Aden Wong, left to right, "
                   "holding their first, second and third place certificates.",
        },
        # The day in order: the pits in the morning, the matches, the awards.
        "groups": [
            {
                "title": "Pits",
                "photos": [
                    {"src": "DSC_0049.JPG",
                     "alt": "The Arcadia High School gym set up for the day, teams working at rows of tables."},
                    {"src": "DSC_0043.JPG",
                     "alt": "Two students behind the front table, the award certificates laid out in front of them."},
                    {"src": "DSC_0041.JPG",
                     "alt": "An adult talks with three students at their pit table, their robot on a practice Hill."},
                    {"src": "DSC_0072.JPG",
                     "alt": "A laptop open to MakeCode, with the robot it programs parked in front of it."},
                    {"src": "DSC_0070.JPG",
                     "alt": "Close-up of a kit robot: the micro:bit, its wiring and two black wheels."},
                    # Cropped above the team's name card, which lists the students.
                    {"src": "DSC_0091.JPG", "crop": (0.0, 0.0, 1.0, 0.84),
                     "alt": "Three students pose at their pit table, hands on their robot beside the laptop."},
                    {"src": "DSC_0073.JPG",
                     "alt": "Two students at a pit table, one at the laptop, their robot on a practice Hill."},
                    {"src": "DSC_0089.JPG",
                     "alt": "Two students smile at the camera from their pit table, a practice Hill in front of them."},
                    {"src": "DSC_0093.JPG",
                     "alt": "A student at a laptop looks up at the camera, a robot beside the keyboard."},
                    {"src": "DSC_0097.JPG",
                     "alt": "A robot on a practice Hill beside a laptop while its team tests their code."},
                    {"src": "DSC_0081.JPG",
                     "alt": "A student is interviewed on camera by the STEMsters media team."},
                ],
            },
            {
                "title": "Matches",
                "photos": [
                    {"src": "4F081C90-93B0-472C-A22D-6B9ECAF32CAE.jpg",
                     "alt": "Two competitors set their robots on the Hill before a match."},
                    {"src": "3CA03C13-F7DE-4F8E-98D6-4466BE0C0DBD.jpg",
                     "alt": "Two robots face off on the Hill in front of the Arcadia High School A."},
                    {"src": "IMG_5010.DNG",
                     "alt": "A competitor bites a knuckle, watching two robots meet on the Hill."},
                    {"src": "IMG_5025.DNG",
                     "alt": "Two robots on the Hill's outer slope, a micro:bit's LED face lit on one of them."},
                    {"src": "22429E2E-B964-4550-AD6E-6B6111B5E08C.jpg",
                     "alt": "Two robots locked together on the Hill, the Arcadia A on the wall behind."},
                    {"src": "4D9C50FD-4DDF-4520-B40B-B1B48F70E4B3.jpg",
                     "alt": "Two competitors lean in close to watch their robots on the Hill."},
                    {"src": "IMG_4997.DNG",
                     "alt": "One robot has been pushed off the Hill onto the table while the other holds the slope."},
                    {"src": "IMG_5049.DNG",
                     "alt": "Two robots push against each other on the Hill, LEDs lit."},
                    {"src": "IMG_5008.DNG",
                     "alt": "A competitor crouches to eye level with the Hill during a match."},
                    {"src": "IMG_5054.DNG",
                     "alt": "A red robot tips off the edge of the Hill while its opponent stays on the slope."},
                    {"src": "B99EE969-BBB5-44F3-AD05-6C8803E0957D.jpg",
                     "alt": "Looking down on the Hill, a red robot and a robot with an ultrasonic sensor on opposite sides."},
                    {"src": "F7C1FEFD-EA3D-4074-94DE-32A12CF90954.jpg",
                     "alt": "A competitor places a robot on the Hill, the bleachers behind."},
                    {"src": "IMG_5075.DNG",
                     "alt": "Two robots collide on the Hill's yellow slope."},
                    {"src": "IMG_4999.DNG",
                     "alt": "A match under way on the gym floor, competitors standing at the table."},
                ],
            },
            {
                "title": "Awards",
                "photos": [
                    {"src": "DSC_0075.JPG",
                     "alt": "The first, second and third place certificates laid out beside the Hill."},
                    {"src": "867452899_1009036315553017_2897763393915498215_n.jpg",
                     "alt": "Advaith Sai Pragasthya Atluri holds up the first place certificate "
                            "as the Bambu Lab A1 printer is carried in."},
                ],
            },
        ],
    },
]


def all_photos(event: dict) -> list[dict]:
    """Every photo an event lists, the champions photo first.

    The build tool cuts exactly this set, and the test that checks nothing
    listed is missing walks exactly this set, so the two cannot drift apart.
    """
    photos = []
    if event.get("champions_photo"):
        photos.append(event["champions_photo"])
    for group in event.get("groups", []):
        photos.extend(group.get("photos", []))
    return photos
