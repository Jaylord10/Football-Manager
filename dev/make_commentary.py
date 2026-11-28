"""Make the commentary's sound files with ElevenLabs (28 Nov) - run on Jay's PC, where his key is.

  python dev/make_commentary.py voices              the voices on your ElevenLabs account (name and id)
  python dev/make_commentary.py use comm <id>       the commentator's voice  (and: use co <id> - the co-commentator)
  python dev/make_commentary.py plan                what's still to make, how many characters, what you've got left
  python dev/make_commentary.py make [N]            make them (all, or the first N) - skips any already made
  python dev/make_commentary.py test comm|co        one line in that voice, to hear it before making the rest

Your key: in a file called elevenlabs_key.txt in the game folder (it never goes into the repo), or the
ELEVENLABS_API_KEY setting.

What gets made (data/commentary/audio/<voice>/<id>.mp3):
  - every line in data/commentary/lines.json (comm = the commentator, co = the co-commentator)
  - the commentator saying every player's surname - and the full name where two in one squad share a surname -
    for every club in the English game (from your career save, saves/career.json; or the starting world)
  - the club names ("Northwick") and the scorelines ("two-one", "one-all") up to 7 goals
A line whose text you've changed is made again; anything already made isn't paid for twice.
The model: eleven_flash_v2_5 (fast and the cheapest per character) - change "model" in data/commentary/voices.json.
"""
import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.dirname(HERE)
sys.path.insert(0, W)
BANK = os.path.join(W, "data", "commentary", "lines.json")
VOICES = os.path.join(W, "data", "commentary", "voices.json")
AUDIO = os.path.join(W, "data", "commentary", "audio")
INDEX = os.path.join(AUDIO, "made.json")              # clip -> the text it was made from (to spot changes)
API = "https://api.elevenlabs.io/v1"
DEFAULTS = {"model": "eleven_flash_v2_5", "comm": "", "co": "",
            # (the commentator a bit livelier - less stable, more style; the co-commentator calmer)
            "settings": {"comm": {"stability": 0.35, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True},
                         "co": {"stability": 0.55, "similarity_boost": 0.8, "style": 0.15, "use_speaker_boost": True}}}


def key():
    k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    f = os.path.join(W, "elevenlabs_key.txt")
    if not k and os.path.exists(f):
        k = open(f).read().strip()
    if not k:
        sys.exit("No ElevenLabs key: put it in a file called elevenlabs_key.txt in the game folder.")
    return k


def call(path, body=None, raw=False):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"xi-api-key": key(), "Content-Type": "application/json",
                                          "Accept": "audio/mpeg" if raw else "application/json"},
                                 method="POST" if body is not None else "GET")
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                return data if raw else json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:                  # (too many at once: wait and try again)
                time.sleep(3 * (attempt + 1))
                continue
            msg = e.read().decode(errors="replace")[:400]
            sys.exit(f"ElevenLabs said no ({e.code}): {msg}")
        except urllib.error.URLError as e:
            if attempt < 4:
                time.sleep(3)
                continue
            sys.exit(f"Couldn't reach ElevenLabs: {e}")


def voices_cfg():
    cfg = dict(DEFAULTS)
    if os.path.exists(VOICES):
        cfg.update(json.load(open(VOICES)))
    return cfg


def short(name):
    for suf in (" FC", " AFC", " F.C."):
        if name.endswith(suf):
            return name[: -len(suf)]
    return name


def squads():
    """{club name: [player names]} for the English clubs - your career if there's one, else the starting world."""
    save = os.path.join(W, "saves", "career.json")
    out = {}
    if os.path.exists(save):
        c = json.load(open(save))
        for cl in c["clubs"]:
            if cl.get("league") in ("pl", "d1"):
                out[cl["name"]] = [p["Name"] for p in cl.get("players", [])] + \
                                  [p["Name"] for p in cl.get("academy", []) if isinstance(p, dict) and "Name" in p]
        for p in c.get("free_agents", []) or []:
            if isinstance(p, dict) and "Name" in p:
                out.setdefault("(free agents)", []).append(p["Name"])
        if out:
            return out
    clubs = {}
    for f in ("clubs.csv", "d1_clubs.csv"):
        for r in csv.DictReader(open(os.path.join(W, "data", "world", f))):
            clubs[r["id"]] = r["name"]
    for f in ("players.csv", "d1_players.csv"):
        for r in csv.DictReader(open(os.path.join(W, "data", "world", f))):
            out.setdefault(clubs.get(r["club"], r["club"]), []).append(r["Name"])
    return out


def wanted():
    """[(voice, clip id, text)] - everything the commentary can say."""
    from gameplay.commentary import slug, score_text
    out = []
    for moment, m in json.load(open(BANK))["moments"].items():
        for l in m["lines"]:
            out.append((m["voice"], l["id"], l["text"]))
    names, seen = [], set()
    for club, players in squads().items():
        if club != "(free agents)":
            out.append(("comm", "club_" + slug(short(club)), short(club) + "."))
        sur = Counter(n.split()[-1] for n in players if n.strip())
        for n in players:
            n = n.strip()
            if not n:
                continue
            s = n.split()[-1]
            for cid, text in (("name_" + slug(s), s), ("fname_" + slug(n), n) if sur[s] > 1 else (None, None)):
                if cid and cid not in seen:
                    seen.add(cid)
                    names.append(("comm", cid, text + "."))
    out += names
    for a in range(8):
        for b in range(a + 1):
            out.append(("comm", f"score_{a}_{b}", score_text(a, b) + "."))
    return out


def made():
    return json.load(open(INDEX)) if os.path.exists(INDEX) else {}


def todo():
    m = made()
    return [(v, c, t) for v, c, t in wanted()
            if m.get(f"{v}/{c}") != t or not os.path.exists(os.path.join(AUDIO, v, c + ".mp3"))]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    cfg = voices_cfg()
    if cmd == "voices":
        for v in call("/voices")["voices"]:
            lab = v.get("labels") or {}
            print(f"{v['voice_id']}  {v['name']:24s} {lab.get('accent', '')} {lab.get('gender', '')} "
                  f"{lab.get('description', '') or lab.get('use_case', '')}")
        print("\nThen: python dev/make_commentary.py use comm <id>   and   use co <id>")
        return
    if cmd == "use":
        who, vid = sys.argv[2], sys.argv[3]
        if who not in ("comm", "co"):
            sys.exit("use comm <id> (the commentator) or use co <id> (the co-commentator)")
        cfg[who] = vid
        os.makedirs(os.path.dirname(VOICES), exist_ok=True)
        json.dump({k: cfg[k] for k in ("model", "comm", "co", "settings")}, open(VOICES, "w"), indent=1)
        print(f"{'Commentator' if who == 'comm' else 'Co-commentator'}: {vid}")
        return
    if cmd == "plan" or cmd == "make":
        t = todo()
        chars = sum(len(x[2]) for x in t)
        print(f"To make: {len(t)} clips, {chars:,} characters "
              f"({sum(1 for x in t if x[1].startswith(('name_', 'fname_')))} names)")
        try:
            sub = call("/user/subscription")
            left = sub.get("character_limit", 0) - sub.get("character_count", 0)
            print(f"Your plan ({sub.get('tier', '?')}): {left:,} credits left this month "
                  f"(of {sub.get('character_limit', 0):,})")
            per = 0.5 if "flash" in cfg["model"] or "turbo" in cfg["model"] else 1.0
            print(f"This would use about {int(chars * per):,} credits with {cfg['model']}")
        except SystemExit as ex:
            print("(Couldn't check your credits:", ex, ")")
        if cmd == "plan":
            return
        if not cfg.get("comm") or not cfg.get("co"):
            sys.exit("Pick the voices first: python dev/make_commentary.py voices")
        n = int(sys.argv[2]) if len(sys.argv) > 2 else len(t)
        m = made()
        for i, (v, c, text) in enumerate(t[:n]):
            audio = call(f"/text-to-speech/{cfg[v]}?output_format=mp3_44100_128",
                         {"text": text, "model_id": cfg["model"], "voice_settings": cfg["settings"][v]}, raw=True)
            os.makedirs(os.path.join(AUDIO, v), exist_ok=True)
            open(os.path.join(AUDIO, v, c + ".mp3"), "wb").write(audio)
            m[f"{v}/{c}"] = text
            if i % 10 == 9 or i == n - 1:
                json.dump(m, open(INDEX, "w"), indent=0)
                print(f"  {i + 1}/{n}  {text}")
        print("Done.")
        return
    if cmd == "test":
        who = sys.argv[2] if len(sys.argv) > 2 else "comm"
        text = {"comm": "And it's a goal! Dawson makes no mistake!",
                "co": "That's clinical. You just can't defend that."}[who]
        audio = call(f"/text-to-speech/{cfg[who]}?output_format=mp3_44100_128",
                     {"text": text, "model_id": cfg["model"], "voice_settings": cfg["settings"][who]}, raw=True)
        out = os.path.join(W, f"commentary_test_{who}.mp3")
        open(out, "wb").write(audio)
        print("Made", out, "- have a listen")
        return
    sys.exit(__doc__)


if __name__ == "__main__":
    main()
