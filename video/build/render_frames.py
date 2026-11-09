#!/usr/bin/env python3
"""Render the six walkthrough slides at 1920x1080. No em or en dashes in any text."""
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
BG = (13, 20, 30)
PANEL = (22, 34, 48)
PANEL2 = (28, 44, 62)
INK = (238, 243, 247)
MUTED = (168, 184, 199)
TEAL = (87, 199, 163)
RED = (224, 93, 68)
AMBER = (232, 178, 75)
LINE = (70, 92, 114)

FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def font(path, size):
    return ImageFont.truetype(path, size)

def text_c(d, cx, y, s, f, fill=INK):
    d.text((cx, y), s, font=f, fill=fill, anchor="ma")
    return y + f.size

def text_l(d, x, y, s, f, fill=INK):
    d.text((x, y), s, font=f, fill=fill, anchor="la")
    return y + f.size

def header(d, s):
    text_l(d, 110, 78, s, font(FB, 40), TEAL)
    d.line([(110, 148), (1810, 148)], fill=LINE, width=3)

def canvas():
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)

def rrect(d, box, radius, **kw):
    d.rounded_rectangle(box, radius=radius, **kw)

# ---------------------------------------------------------------- slide 1
def slide1():
    img, d = canvas()
    text_c(d, 960, 150, "SWARM ALIGNMENT HACKATHON", font(FB, 38), TEAL)
    text_c(d, 960, 300, "Alignment Does", font(FB, 118))
    text_c(d, 960, 440, "Not Compose", font(FB, 118))
    d.line([(560, 640), (1360, 640)], fill=TEAL, width=5)
    text_c(d, 960, 690, "Governed Execution Forests for Agent Swarms", font(FR, 50), MUTED)
    text_c(d, 960, 790, "Per-agent governance does not add up to swarm safety.", font(FR, 40), MUTED)
    text_c(d, 960, 950, "Muntaser Syed", font(FB, 42))
    return img

# ---------------------------------------------------------------- slide 2
def slide2():
    img, d = canvas()
    header(d, "THE FAILURE: EVERY AGENT BEHAVES, THE SWARM FAILS")
    rrect(d, (110, 210, 930, 560), 24, fill=PANEL)
    text_c(d, 520, 250, "651", font(FB, 190), RED)
    text_c(d, 520, 470, "credits spent, no swarm controls", font(FR, 38), MUTED)
    rrect(d, (990, 210, 1810, 560), 24, fill=PANEL)
    text_c(d, 1400, 250, "300", font(FB, 190), TEAL)
    text_c(d, 1400, 470, "credits in the shared pool", font(FR, 38), MUTED)
    rows = [
        ("Delegation depth reached", "4"),
        ("Items completed", "120 of 120"),
        ("Task outcome", "FAILED on cost"),
    ]
    y = 640
    for label, val in rows:
        text_l(d, 160, y, label, font(FR, 46), MUTED)
        d.text((1760, y), val, font=font(FB, 46), fill=INK, anchor="ra")
        y += 84
    text_c(d, 960, 940, "No agent broke its own rules. Delegating was always the cheapest move.", font(FB, 42))
    return img

# ---------------------------------------------------------------- slide 3
def mini_tree(d, cx, top):
    d.ellipse([cx - 17, top, cx + 17, top + 34], fill=TEAL)
    for dx in (-46, 46):
        d.line([(cx, top + 34), (cx + dx, top + 74)], fill=LINE, width=4)
        d.ellipse([cx + dx - 13, top + 74, cx + dx + 13, top + 100], fill=MUTED)

def slide3():
    img, d = canvas()
    header(d, "THE CONSTRUCTION: GOVERN THE FOREST, NOT JUST THE TREES")
    names = ["atlas", "gale", "birch", "cedar", "dune"]
    bw, gap, x0, top = 300, 42, 110, 225
    centers = []
    for i, n in enumerate(names):
        x = x0 + i * (bw + gap)
        rrect(d, (x, top, x + bw, top + 235), 20, fill=PANEL)
        mini_tree(d, x + bw // 2, top + 28)
        text_c(d, x + bw // 2, top + 152, n, font(FB, 42))
        text_c(d, x + bw // 2, top + 200, "own execution tree", font(FR, 26), MUTED)
        centers.append(x + bw // 2)
    for a, b in zip(centers, centers[1:]):
        y = top + 110
        d.line([(a + 150, y), (b - 150, y)], fill=AMBER, width=6)
        d.polygon([(b - 150, y), (b - 172, y - 11), (b - 172, y + 11)], fill=AMBER)
    text_c(d, 960, 500, 'every arrow is a "delegate" action, recorded in the delegator\'s tree', font(FR, 36), AMBER)
    rrect(d, (110, 585, 1810, 752), 24, fill=PANEL2)
    text_c(d, 960, 618, "ONE SHARED BUDGET POOL: 300 CREDITS", font(FB, 48))
    text_c(d, 960, 686, "every charge from every tree settles against the same pool", font(FR, 32), MUTED)
    text_l(d, 110, 800, "Depth gate: delegations deeper than depth 2 are denied.", font(FR, 40))
    text_l(d, 110, 865, "A delegation landing exactly at depth 2 needs approval first.", font(FR, 40))
    text_l(d, 110, 930, "Denials and approvals are recorded in the forest, and the run replays exactly.", font(FR, 40))
    return img

# ---------------------------------------------------------------- slide 4
def slide4():
    img, d = canvas()
    header(d, "THE DRIFT LAYER: GALE, WATCHED BY PAGE HINKLEY")
    text_l(d, 110, 195, "Gale's executed action costs, in order. Onset: work cost multiplied by 4 at action 7.", font(FR, 38), MUTED)
    costs = ["1", "1", "1", "1", "1", "1", "40"]
    bw, gap, x0, top = 215, 33, 110, 300
    for i, c in enumerate(costs):
        x = x0 + i * (bw + gap)
        hot = i == 6
        rrect(d, (x, top, x + bw, top + 190), 20, fill=(74, 34, 28) if hot else PANEL)
        text_c(d, x + bw // 2, top + 22, "action %d" % (i + 1), font(FR, 30), MUTED)
        text_c(d, x + bw // 2, top + 70, c, font(FB, 84), RED if hot else INK)
    text_c(d, x0 + 6 * (bw + gap) + bw // 2, top + 205, "was 10", font(FR, 30), RED)
    rrect(d, (110, 590, 1810, 762), 24, fill=PANEL2)
    text_c(d, 960, 620, "ALARM AT ACTION 7", font(FB, 52), AMBER)
    text_c(d, 960, 690, "detection delay 0   |   no false alarms before onset", font(FR, 36), MUTED)
    rows = [
        "Verdict recorded. Gale is frozen. Further delegations are refused.",
        "4 queued items reassigned. Exactly 1 inflated action landed.",
        "Run completes at 281 credits, inside the pool.",
    ]
    y = 818
    for r in rows:
        text_l(d, 110, y, r, font(FR, 42))
        y += 72
    return img

# ---------------------------------------------------------------- slide 5
def results():
    img, d = canvas()
    text_l(d, 110, 78, "RESULTS: SAME SWARM, THREE GOVERNANCE SCENARIOS", font(FB, 40), TEAL)
    d.line([(110, 148), (1810, 148)], fill=LINE, width=3)
    cols = [110, 700, 1060, 1420]
    colw = [590, 360, 360, 390]
    headers = ["", "Ungoverned", "Governed", "Governed + drift"]
    rows = [
        ("Spend (credits)", "651", "251", "281"),
        ("Pool (credits)", "300", "300", "300"),
        ("Max depth", "4", "2", "2"),
        ("Gate denials", "0", "22", "22"),
        ("Approvals granted", "0", "22", "22"),
        ("Task success", "NO", "YES", "YES"),
    ]
    y = 200
    rrect(d, (90, y - 14, 1830, y + 74), 14, fill=PANEL2)
    for cx, cw, htxt in zip(cols, colw, headers):
        if htxt:
            text_l(d, cx + 20, y, htxt, font(FB, 40))
    y += 96
    for i, row in enumerate(rows):
        if i % 2 == 0:
            rrect(d, (90, y - 10, 1830, y + 70), 10, fill=PANEL)
        for cx, val in zip(cols, row):
            f = font(FR, 42) if cx == cols[0] else font(FB, 42)
            fill = INK
            if row[0] == "Task success":
                fill = RED if val == "NO" else TEAL
            text_l(d, cx + 20, y, val, f, MUTED if cx == cols[0] else fill)
        y += 84
    y += 26
    text_l(d, 110, y, "Replay trace digest matches in all three conditions.", font(FB, 42)); y += 66
    text_l(d, 110, y, "Step functions invoked during replay: 0.", font(FB, 42)); y += 66
    text_l(d, 110, y, "Test suite: 9 of 9 passing.", font(FB, 42))
    return img

# ---------------------------------------------------------------- slide 6
def slide6():
    img, d = canvas()
    text_c(d, 960, 300, "Govern the forest,", font(FB, 84))
    text_c(d, 960, 410, "not just the trees.", font(FB, 84))
    d.line([(560, 560), (1360, 560)], fill=TEAL, width=5)
    text_c(d, 960, 620, "Honest limits: deterministic agents, one task family, synthetic drift.", font(FR, 38), MUTED)
    text_c(d, 960, 760, "github.com/jemsbhai/swarm-forest", font(FB, 54), TEAL)
    text_c(d, 960, 880, "Built on pollard 1.6.2 and epicormic 0.2.0,", font(FR, 36), MUTED)
    text_c(d, 960, 930, "the author's preexisting published packages.", font(FR, 36), MUTED)
    return img

if __name__ == "__main__":
    import os
    out = os.path.expanduser("~/workspace/swarm-forest/video/build/frames")
    os.makedirs(out, exist_ok=True)
    for i, fn in enumerate([slide1, slide2, slide3, slide4, results, slide6], start=1):
        fn().save(os.path.join(out, "f%d.png" % i))
        print("frame", i, "ok")
