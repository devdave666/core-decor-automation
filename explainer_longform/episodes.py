"""
Episode definitions for the long-form faceless explainer.

An episode is a table of "upgrades" applied cumulatively to one base room.
build() expands the table into:
  images -- key -> generation spec (base prompt, edit of another image, or alt angle)
  beats  -- narration lines, each with a shot template; the renderer splits shots
            further so no cut runs longer than render.MAX_SHOT_S.
"""

ROOM_STYLE = (
    "Ultra-photorealistic interior photograph, 16:9 landscape, shot on a full-frame "
    "camera with a 24mm lens, razor-sharp focus and fine material detail everywhere, "
    "natural colour, no text, no people, no watermark."
)

BASE_PROMPT = (
    f"{ROOM_STYLE} A plain, builder-grade suburban living room that looks bland and "
    "unstyled: flat beige walls, a small grey fabric sofa along the back wall on the "
    "left, a thin white coffee table in front of it, one tiny beige rug floating in the "
    "middle of a pale laminate wood floor, a large window on the right with short thin "
    "white curtains hung just above the window frame, a harsh flat ceiling light, "
    "completely bare walls, and a little clutter (remote controls, a mug) on the "
    "table. Flat daytime light from the window. Camera at eye level, straight-on across "
    "the room, showing the sofa wall and the window."
)

EDIT_TEMPLATE = (
    "Edit this photo. Change ONLY the following: {change} Keep the camera angle, room "
    "layout, window, floor, sofa position and everything not mentioned exactly the "
    "same. Photorealistic, razor-sharp, 16:9."
)

ANGLE_TEMPLATE = (
    "Show this exact same room, with every design element identical (same colours, "
    "furniture, decor, lighting), but photographed from a different camera position: "
    "{angle} Photorealistic, razor-sharp, 16:9."
)

UPGRADES = [
    {
        "title": "PAINT THE WALLS",
        "change": "Repaint all the walls a rich, warm, deep greige (muted taupe) in a matte finish. Ceiling and trim stay white.",
        "angle": "camera moved to the left corner looking diagonally toward the window.",
        "focus_before": "the flat beige wall behind the sofa",
        "focus_after": "the deep warm greige wall behind the sofa",
        "lines": [
            "[excited] Number one. Paint. Flat beige walls make a room feel temporary.",
            "Switch to a deep, warm greige, and the whole room suddenly has depth.",
            "Darker, muted colors hide flaws, and make every piece of furniture pop against the wall.",
            "Quick tip. Sample two colors first, and look at them in the evening light. Around fifty dollars a gallon.",
        ],
    },
    {
        "title": "HANG CURTAINS HIGH",
        "change": "Replace the thin short curtains with floor-to-ceiling cream linen curtains hung close to the ceiling, extending wide past both sides of the window frame, touching the floor.",
        "angle": "camera on the right side of the room, lower angle, looking along the window wall.",
        "focus_before": "the short thin curtains hanging just above the window",
        "focus_after": "the floor-to-ceiling linen curtains",
        "lines": [
            "Number two. Look at these curtains. Hung right on the window frame, they shrink the whole room.",
            "Hang them near the ceiling, and let them touch the floor.",
            "Your ceilings look taller, the window looks huge, and it's the exact same window.",
            "Tip. Mount the rod about four inches below the ceiling, and buy extra wide panels so they look full. Around eighty dollars.",
        ],
    },
    {
        "title": "GO BIG ON THE RUG",
        "change": "Replace the small rug with a large neutral textured wool rug (about 8 by 10 feet) that extends under the front legs of the sofa and coffee table.",
        "angle": "camera closer and lower, three-quarter view of the sofa and the rug.",
        "focus_before": "the tiny rug in the middle of the floor",
        "focus_after": "the large textured wool rug",
        "lines": [
            "Number three. This tiny rug floats in the middle of the room like a little island.",
            "Go bigger. Way bigger. The front legs of every piece should sit on it.",
            "A large rug ties the furniture together, and makes the whole space feel planned.",
            "Tip. In most living rooms, aim for eight by ten. A good one starts around a hundred and fifty dollars.",
        ],
    },
    {
        "title": "LAYER YOUR LIGHTING",
        "change": "Turn off the harsh overhead light. Add a tall floor lamp beside the sofa and a table lamp on a small side table, both glowing a warm cozy yellow, with soft warm pools of evening light.",
        "angle": "camera on the left side, mid-height, looking across the sofa toward the lamps.",
        "focus_before": "the harsh flat ceiling light",
        "focus_after": "the glowing warm floor lamp and table lamp",
        "lines": [
            "Number four. This is the one everyone skips. One bright ceiling light is the fastest way to make a room look cheap.",
            "Add lamps at different heights, and use warm bulbs.",
            "Soft pools of light create mood, and mood is what expensive rooms are really made of.",
            "Tip. Look for twenty-seven hundred Kelvin bulbs. Each lamp can be under forty dollars.",
        ],
    },
    {
        "title": "HANG OVERSIZED ART",
        "change": "Hang one very large framed abstract artwork in warm neutral tones, centered above the sofa, in a thin oak frame, about two thirds the width of the sofa.",
        "angle": "camera straight-on, slightly closer, centred on the sofa and artwork.",
        "focus_before": "the bare empty wall above the sofa",
        "focus_after": "the large framed abstract artwork above the sofa",
        "lines": [
            "Number five. Bare walls, or tiny frames floating in space.",
            "Hang one huge piece instead, about two thirds the width of your sofa.",
            "Big art makes a statement. Small art just looks lost.",
            "Tip. A large print in a simple frame costs far less than original art. Around eighty dollars.",
        ],
    },
    {
        "title": "LAYER TEXTURES",
        "change": "Add layered textiles: a chunky knit throw draped over the sofa arm, three mixed-texture pillows (linen, boucle, velvet) in earthy tones on the sofa, and a cream boucle accent chair on the right side of the rug.",
        "angle": "camera at a three-quarter angle focused on the sofa pillows and accent chair.",
        "focus_before": "the plain flat grey sofa",
        "focus_after": "the layered pillows and chunky knit throw on the sofa",
        "lines": [
            "Number six. Everything in this room is the same flat texture.",
            "Mix in wool, linen, boucle and velvet.",
            "Texture adds richness your eye can feel, even through a screen. Keep the colors close, and vary the fabrics.",
            "Tip. Start with pillows. Swap the covers, not the inserts, and it costs about a hundred dollars.",
        ],
    },
    {
        "title": "ADD GREENERY",
        "change": "Add a large leafy fiddle-leaf fig plant in a woven basket planter in the corner beside the window, and a small green plant in a ceramic pot on the coffee table.",
        "angle": "camera from the far side of the room, wide, showing the window corner and the large plant.",
        "focus_before": "the empty corner beside the window",
        "focus_after": "the large leafy plant in the woven basket",
        "lines": [
            "Number seven. Something's missing. This room feels lifeless.",
            "Add one big plant in a corner, and one small one on the table.",
            "Living things add color, height and softness that no furniture can.",
            "Tip. A basket planter hides the ugly plastic pot. Around fifty dollars, all in.",
        ],
    },
    {
        "title": "STYLE THE SURFACES",
        "change": "Style the coffee table with a wooden tray holding a stack of two books, a candle and a small ceramic vase with a few stems. Remove the remotes, the mug and all clutter from every surface.",
        "angle": "camera low and close, looking across the styled coffee table toward the sofa.",
        "focus_before": "the cluttered coffee table with remotes and a mug",
        "focus_after": "the styled coffee table tray with books, candle and vase",
        "lines": [
            "Number eight. Clutter makes even a pricey room look cheap.",
            "Clear every surface, then style small groups in threes.",
            "A tray, a candle, a vase. Odd numbers, different heights. That's the whole trick.",
            "Tip. A tray corrals the small stuff, so the table always looks tidy. Under thirty dollars.",
        ],
    },
]

HOOK = ("[excited] This is the exact same boring living room. [pause] Eight cheap "
        "changes later, it looks like it costs ten times more. Let's go.")
INTRO = ("Here's where we start. Builder beige walls, a tiny rug, and lighting that "
         "makes everything look flat.")
OUTRO = ("[warm] That's it. Same room, eight cheap changes, and a completely different "
         "feeling. [pause] Subscribe for more room makeovers, and tell me in the "
         "comments which one you'd try first.")


def _key(i):
    return f"u{i}"


def build():
    n = len(UPGRADES)
    final = _key(n)
    images = {"base": {"prompt": BASE_PROMPT}}
    for i, u in enumerate(UPGRADES, 1):
        prev = "base" if i == 1 else _key(i - 1)
        images[_key(i)] = {"edit_of": prev,
                           "prompt": EDIT_TEMPLATE.format(change=u["change"])}
        images[f"{_key(i)}_alt"] = {"edit_of": _key(i),
                                    "prompt": ANGLE_TEMPLATE.format(angle=u["angle"])}

    beats = [
        {"id": "hook", "text": HOOK, "shots": [
            {"image": "base", "move": "push"},
            {"reveal": ["base", final]},
            {"image": f"{final}_alt", "move": "pan_r"},
        ]},
        {"id": "intro", "text": INTRO, "shots": [
            {"image": "base", "move": "push"},
            {"image": "base", "move": "detail", "focus": "the harsh flat ceiling light"},
            {"image": "base", "move": "pan_l"},
        ]},
    ]
    for i, u in enumerate(UPGRADES, 1):
        prev = "base" if i == 1 else _key(i - 1)
        cur, alt = _key(i), f"{_key(i)}_alt"
        a, b, c, d = u["lines"]
        meta = {"badge": f"UPGRADE {i}/{n}", "upgrade": i}
        beats += [
            {"id": f"u{i}a", "text": a, "title": u["title"], **meta, "shots": [
                {"image": prev, "move": "push"},
                {"image": prev, "move": "detail", "focus": u["focus_before"]},
            ]},
            {"id": f"u{i}b", "text": b, **meta, "shots": [
                {"reveal": [prev, cur]},
                {"image": cur, "move": "pull"},
            ]},
            {"id": f"u{i}c", "text": c, **meta, "shots": [
                {"image": cur, "move": "detail", "focus": u["focus_after"]},
                {"image": alt, "move": "pan_r"},
                {"image": cur, "move": "push"},
            ]},
            {"id": f"u{i}d", "text": d, **meta, "shots": [
                {"image": alt, "move": "detail", "focus": u["focus_after"]},
                {"image": cur, "move": "pan_l"},
            ]},
        ]
    beats.append({"id": "outro", "text": OUTRO, "shots": [
        {"reveal": ["base", final]},
        {"image": final, "move": "pull"},
        {"image": f"{final}_alt", "move": "push"},
    ]})

    return {
        "slug": "ep01",
        "title": "8 Cheap Changes That Make a Living Room Look Expensive",
        "thumb_text": "LOOKS EXPENSIVE",
        "description": (
            "Eight cheap upgrades that transform a plain, builder-grade living room "
            "into one that looks far more expensive: paint, high curtains, a bigger "
            "rug, layered lighting, oversized art, texture, greenery and styling.\n\n"
            "Images are AI-generated for illustration. Narration is a synthetic voice."
        ),
        "images": images,
        "beats": beats,
        "final": final,
    }
