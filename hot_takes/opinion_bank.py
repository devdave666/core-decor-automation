"""
Opinion bank for the "Hot Takes" content type.

Same philosophy as caption_bank.py one level up: a fixed, hand-written pool cycled
deterministically via a committed index file, not generated per-run. No LLM call,
no runtime cost, no risk of a model quietly drifting off-brand over time.

DELIBERATELY GENERIC, not specific — read this before adding entries. An earlier
version referenced specific colors and materials ("Beige is boring", "That's a lot
of brass for one room"). The pipeline cycles through application photos with no
attribute awareness at all — it doesn't know or check what's actually IN a given
photo, so a line calling out "beige" can land on a moody dark room with no beige
anywhere in it, which reads as a visible mistake, not a stylistic choice. Every
entry here is an attitude or philosophy about design/home life in general, not a
claim about a specific color, material, or object — so it stays compatible with
whatever photo the rotation happens to land on. If adding new entries, apply the
same test: would this line still make sense over ANY of the 50 application photos,
not just the one you're picturing while writing it?
"""

OPINIONS = [
    ("They: It's just a house.", "Me: It is never just a house."),
    ("They: You're overthinking this room.", "Me: There is no such thing as overthinking a room."),
    ("They: A house is done when it's done.", "Me: A house is never done."),
    ("They: Nobody notices the details.", "Me: I notice everything."),
    ("They: You've redone this room three times.", "Me: And I'll do it again."),
    ("They: It's just a corner of a room.", "Me: There are no small corners."),
    ("They: That took way too long to get right.", "Me: Correct amount of time."),
    ("They: You could have just left it alone.", "Me: I could have. I didn't."),
    ("They: Most people wouldn't spend this much time on a room.", "Me: I am not most people."),
    ("They: It looked fine before.", "Me: Fine is not the goal."),
    ("They: You're never satisfied.", "Me: Correct."),
    ("They: This is a lot of effort for one room.", "Me: This is the appropriate amount of effort."),
    ("They: Just buy whatever's on sale.", "Me: Absolutely not."),
    ("They: A space is just a space.", "Me: A space is a mood."),
    ("They: You should be done decorating by now.", "Me: I will never be done."),
    ("They: Nobody else will notice this changed.", "Me: I will notice."),
    ("They: This room already looks good.", "Me: Good is not the same as right."),
    ("They: You spend too much time on this.", "Me: I spend exactly enough time on this."),
    ("They: It's just decor.", "Me: It is never just decor."),
    ("They: You can't tell the difference.", "Me: I can always tell the difference."),
    ("They: This is excessive.", "Me: This is thorough."),
    ("They: Just live with it as it is.", "Me: I will not."),
    ("They: A room doesn't need a personality.", "Me: Every room needs a personality."),
    ("They: You'll change your mind about this in a year.", "Me: Probably. I'll deal with it then."),
    ("They: This wasn't necessary.", "Me: It was necessary to me."),
]
