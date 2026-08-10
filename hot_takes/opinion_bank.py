"""
Opinion bank for the "Hot Takes" content type.

Same philosophy as caption_bank.py one level up: a fixed, hand-written pool cycled
deterministically via a committed index file, not generated per-run. No LLM call,
no runtime cost, no risk of a model quietly drifting off-brand over time.

Each entry is a (setup, punchline) pair rendered as two lines of on-screen text —
"They:" / "Me:" by default, matching the reference format this was built from, but
the pipeline treats these as plain text rather than hardcoding the labels, so a
future entry can break that pattern on purpose (e.g. a single bold statement with
no "they/me" framing at all) without needing a code change.
"""

OPINIONS = [
    ("They: Let's just paint the walls.", "Me: No…"),
    ("They: Beige is boring.", "Me: Beige is a personality."),
    ("They: Open shelving is impractical.", "Me: I said what I said."),
    ("They: You don't need a coffee table book.", "Me: We are not the same."),
    ("They: Matching furniture sets are classic.", "Me: Matching is for socks."),
    ("They: One accent wall is enough.", "Me: There is no such thing as enough."),
    ("They: Recessed lighting is fine.", "Me: Recessed lighting is a crime."),
    ("They: A rug should match the sofa.", "Me: A rug should have opinions."),
    ("They: You're overthinking a doorknob.", "Me: There are no small decisions."),
    ("They: Wallpaper is outdated.", "Me: You are outdated."),
    ("They: Just get the beige sectional.", "Me: Absolutely not."),
    ("They: Nobody notices cabinet hardware.", "Me: I notice everything."),
    ("They: Symmetry is overrated.", "Me: Get out of my house."),
    ("They: It's just a hallway.", "Me: There are no 'just' hallways."),
    ("They: Candles are a waste of money.", "Me: Ambiance is not a waste."),
    ("They: All-white kitchens are timeless.", "Me: So is being wrong."),
    ("They: You don't need that many pillows.", "Me: I need exactly that many pillows."),
    ("They: Marble is impractical for a kitchen.", "Me: I did not ask."),
    ("They: A bathroom is just a bathroom.", "Me: A bathroom is a mood."),
    ("They: Warm lighting is dramatic.", "Me: Correct."),
    ("They: You've redone this room three times.", "Me: And I'll do it again."),
    ("They: That's a lot of brass for one room.", "Me: There is no such thing."),
    ("They: Textured walls are a phase.", "Me: I am never leaving this phase."),
    ("They: Nobody cares about grout color.", "Me: I care. Deeply."),
    ("They: It's just a plant.", "Me: It is never just a plant."),
]
