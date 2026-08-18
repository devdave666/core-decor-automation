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
    "okay but the grain on this wood is unreasonable",
    "we don't usually post two boards in one week but here we are",
    "I keep opening this photo just to look at it, no reason",
    "this is what happens when nobody vetoes the stone",
    "honestly didn't think this would make the cut, it did",
    "the second you see the room you'll get why we led with this swatch",
    "not a subtle material board, on purpose",
    "this one almost got scrapped twice",
    "someone in the group chat called this one boring, they were wrong",
    "the veining on this stone did the whole job for us",
    "we usually lead with the room, flipped it this time",
    "this combo shouldn't work on paper and yet",
    "took the long way to get here but the pairing's right",
    "the kind of material board you screenshot and forget why",
    "put this one up against three others, it won",
    "this is the one the client actually picked, for once",
    "the finish on this one photographs better than it looks in person, rare",
    "didn't expect the metal to be the star but here we are",
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
    "drop a 🤍 if you'd actually live in this",
    "this is the last board before we start the room for real",
    "genuinely can't pick a favorite material here, don't make me",
    "if this one gets saved enough we'll do a full room breakdown",
    "the client hasn't seen this pairing yet, wish us luck",
    "we go through more of these than actually make it to a room",
    "half the team wanted a different metal, they lost",
    "this is what's sitting on the desk right now, unfinished",
    "no hashtag wall today either, some things speak for themselves",
    "already regret not posting this one sooner",
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


# ---------------------------------------------------------------------------
# Single-product drops — one swatch, many application shots of the SAME
# product, sourced from a one-off Drive folder rather than the rotating
# c-/d-series pool. Short link-in-bio caption for IG/FB/TikTok/YouTube, long
# SEO caption for Pinterest. See single_product_reel/single_product_pipeline.py.
# ---------------------------------------------------------------------------

LINK_IN_BIO_HOOKS = [
    "kept coming back to this one so here it is",
    "this material's been living in every room we mock up lately",
    "the one everyone keeps asking about",
    "put this through a few different rooms just to see, results below",
    "this is the material, not the theory of the material",
    "wanted to show this one on more than just the swatch",
    "this is the one that made the shortlist every single time",
    "still the easiest recommend in the whole library",
]

LINK_IN_BIO_TAILS = [
    "link in bio if you want the details on {product}",
    "{product} — link in bio for sourcing",
    "everything on {product} is in the bio link",
    "link in bio, that's where {product} lives",
    "full breakdown of {product} through the bio link",
    "bio link has the rest on {product}",
]


def get_link_in_bio_caption(product_name):
    """
    Short caption for IG/FB/TikTok/YouTube on a single-product drop — a hook line
    plus a natural link-in-bio CTA naming the product, same modular hook/tail
    shape as get_caption() but without an index (one-off run, not a rotation).
    """
    import random

    hook = random.choice(LINK_IN_BIO_HOOKS)
    tail = random.choice(LINK_IN_BIO_TAILS).format(product=product_name)
    hashtags = " ".join(FIXED_HASHTAGS)
    return f"{hook}.\n{tail}\n\n{hashtags}"


PINTEREST_SEO_OPENERS = [
    "{product} is the kind of material that changes how a whole room reads.",
    "If you're planning a space around {product}, here's what to know before you commit to it.",
    "{product} keeps showing up in our material boards for a reason.",
]

PINTEREST_KEYWORD_POOL = [
    "interior design", "home renovation", "material palette", "natural stone",
    "kitchen design", "bathroom design", "living room decor", "moodboard",
    "interior styling", "modern luxury interiors", "organic modern design",
    "warm minimalism", "textured surfaces", "design inspiration",
    "home makeover ideas", "luxury home design",
]


def get_pinterest_seo_caption(product_name):
    """
    Long-form, keyword-front-loaded description for Pinterest SEO — Pinterest's
    own search surfaces reward descriptive, keyword-dense pin text far more than
    the short-hook style used elsewhere, so this is deliberately a different
    shape from get_caption()/get_link_in_bio_caption(), not just a longer
    version of them. Front-loads the product name and top keywords in the first
    sentence, since Pinterest truncates descriptions in search results.
    """
    import random

    opener = random.choice(PINTEREST_SEO_OPENERS).format(product=product_name)
    keywords = random.sample(PINTEREST_KEYWORD_POOL, 6)

    body = (
        f"{opener} Save this pin for {product_name} inspiration — whether you're "
        f"planning a full renovation or just swapping one material at a time, this "
        f"is the kind of finish that pulls a room together instead of competing "
        f"with everything else in it.\n\n"
        f"See it paired against real application shots, not just the swatch card, "
        f"so you know how {product_name} actually reads in a finished space under "
        f"real lighting — the swatch alone rarely tells the whole story.\n\n"
        f"Perfect for {keywords[0]}, {keywords[1]}, and {keywords[2]} boards. Also "
        f"a strong fit if you're collecting ideas around {keywords[3]}, "
        f"{keywords[4]}, or {keywords[5]}.\n\n"
        f"Pin this for later, and tap through for the full sourcing details on "
        f"{product_name} — link in bio."
    )
    return body
