"""
Caption bank, v2 — rewritten to not read as AI-generated.

What actually makes a caption read as AI-written, and what changed here:
  - The "hook line + CTA line + .\\n.\\n.\\n + hashtag wall" structure IS a recognizable
    template by itself, regardless of how good the individual lines are. Removed
    entirely. Hashtags now sit right after the text, sometimes on their own line,
    sometimes trailing the last sentence — inconsistent on purpose, like a real
    person posting between other things.
  - Uniform short-punchy-sentence rhythm ("Two materials, one room, zero guesswork.")
    is itself a tell. Real writing varies — some lines run on, some are a fragment,
    some just trail off.
  - Directive CTAs ("Save this for your next reno.") read as marketing copy. Replaced
    with the kind of aside a person actually adds — a genuine reaction, a half-question,
    sometimes nothing at all.
  - Perfect grammar and consistent capitalization throughout a caption is itself a
    tell. Some lines here start lowercase. Some skip a comma where a person would.

Still fully modular — HOOKS x TAILS still gives hundreds of combinations — but each
piece was rewritten to sound like it was typed on a phone, not generated.
"""

FIXED_HASHTAGS = ["#coredecor", "#materialsofinstagram"]

HOOKS = [
    "the stone alone was worth building this account for",
    "ok this pairing might be my favorite one yet",
    "two materials in and I already know which one wins",
    "not sure why this combo works as well as it does but it does",
    "found the material combo I didn't know I needed",
    "this is the one I keep going back to",
    "the wood grain on this one is doing a lot of work",
    "swatch first, always. this is why",
    "the kind of pairing you don't plan, you just find",
    "genuinely didn't expect these two to work together this well",
    "this is what happens when the stone does the talking",
    "kept this one on the desk for a week before deciding on the room",
    "the metal is the whole reason this works",
    "this one took a few tries to get right",
    "the texture on this stone is unreasonable",
    "still thinking about this one honestly",
    "this is the material board that started the whole room",
    "sometimes the swatch is prettier than the finished room, don't @ me",
    "the kind of quiet luxury that doesn't announce itself",
    "this pairing has been living in my drafts for a week",
    "not everything needs five materials. sometimes two is plenty",
    "the brass on this one catches the light just right",
    "this is the board I'd frame if that wasn't weird",
    "every material here was chosen on purpose, nothing default",
    "this is the version we almost didn't post",
    "the kind of room that starts with a rock, literally",
    "some of these material names are better than the room names honestly",
    "this one's for the people who notice hardware finishes",
    "the swatch doesn't do this stone justice, wait for the room",
    "picked these two, argued about the metal for a while, here's where we landed",
]

TAILS = [
    "which one are you stealing for your own place",
    "tell me the material names without looking, I dare you",
    "this is going straight into the folder of ones we're actually building",
    "curious if anyone else has used this stone before",
    "no CTA today, just wanted to show you this one",
    "more of these coming, we've got a lot of boards to get through",
    "tag whoever's mid-reno right now",
    "this is why we save every material board before the room",
    "happy to talk sourcing if anyone's actually building this",
    "the swatch or the room — which one's the real post",
    "still deciding if this is our favorite one so far",
    "not sponsored, we just really like this stone",
    "save it now, you'll forget the name later",
    "this took longer to get right than it probably looks like",
    "if you know this stone by name, we need to talk",
    "there's a version of this room in warm oak too, might post it",
    "this is what's in the pipeline for the next few rooms",
    "the metal choice was a whole debate, for the record",
    "we go back and forth on which material to lead with every time",
    "",  # sometimes a real post just ends, no tail line at all
]

HASHTAG_POOL = [
    "#interiordesign", "#interiordesigner", "#homedesign", "#luxuryinteriors",
    "#designinspo", "#materialpalette", "#moodboard", "#interiorstyling",
    "#dreamhome", "#homerenovation", "#kitchendesign", "#bathroomdesign",
    "#naturalstone", "#stonecladding", "#travertine", "#marbledesign",
    "#warminteriors", "#organicmodern", "#japandi", "#modernluxury",
    "#mediterraneanstyle", "#midcenturymodern", "#artdecostyle", "#brutalistdesign",
    "#scandinavianstyle", "#coastalstyle", "#frenchcountry", "#tropicalmodern",
    "#wabisabi", "#mountainhome", "#manorstyle", "#industrialdesign",
    "#unlacqueredbrass", "#mixedmetals", "#designdetails", "#interiorinspiration",
    "#homedecor", "#renovationideas", "#luxuryhomes", "#interiorarchitecture",
    "#texturelove", "#materiallibrary", "#designprocess", "#interiordetails",
    "#housetohome", "#beforeandafter",
]

HASHTAGS_PER_POST = 5  # fewer than v1 — a hashtag wall is itself an AI-post tell


def get_caption(index):
    """
    Deterministic — same index always returns the same caption, so only the counter
    file needs to persist between runs. Structure varies per index (not just word
    choice) so consecutive posts don't share a visible template: hashtag placement,
    line breaks, and whether a tail line even exists all shift.
    """
    hook = HOOKS[index % len(HOOKS)]
    tail = TAILS[(index // len(HOOKS)) % len(TAILS)]

    start = (index * HASHTAGS_PER_POST) % len(HASHTAG_POOL)
    rotating = [HASHTAG_POOL[(start + i) % len(HASHTAG_POOL)] for i in range(HASHTAGS_PER_POST)]
    hashtags = " ".join(FIXED_HASHTAGS + rotating)

    # Three different structural shapes, rotated by index, so the caption doesn't
    # always look like "line / line / hashtags" — that shape repeated is itself
    # recognizable regardless of wording.
    shape = index % 3
    if not tail:
        body = hook
    elif shape == 0:
        body = f"{hook}\n{tail}"
    elif shape == 1:
        body = f"{hook} — {tail}"
    else:
        body = f"{hook}.\n\n{tail}"

    if index % 4 == 0:
        return f"{body}\n\n{hashtags}"
    return f"{body} {hashtags}"


def cycle_length():
    """Number of posts before hook/tail combinations start repeating."""
    return len(HOOKS) * len(TAILS)
