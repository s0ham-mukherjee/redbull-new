"""Voice casting — India. Port of the user-provided voice-actor-system.

Faithful port of the original JS scoring (analyzeScript → calculateCompatibility
over a 510-actor Indian voice-actor database), with two additions our writer
needs: a human-readable rationale per match, and a transparency note. Same
weights as the source: language 30 · gender 25 · age 20 · tone 20 · emotion 15
· multilingual diversity 15 → 0-100 compatibility.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

def _data_root() -> Path:
    env = os.environ.get("SAKURASCORE_BACKEND_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "backend 111" / "redbull-thapar-japan"

DATA = _data_root() / "data" / "casting" / "voice_actors.json"

LANGUAGE_MAP = {
    "hindi": ["hindi", "dhanyavad", "shukriya", "achha", "kaun", "kya", "main", "tum", "ji", "ji-hazari", "namaste", "mere"],
    "tamil": ["tamil", "vanakkam", "enakku", "nandri", "vazhga", "naan", "appaa", "poda"],
    "telugu": ["telugu", "namaskaram", "nichay", "intiki", "nenu", "chesina", "kaval", "vachinde"],
    "malayalam": ["malayalam", "engane", "anu", "sambhavam", "oday", "shubham"],
    "marathi": ["marathi", "kasa", "asel", "asali", "hya"],
    "bengali": ["bengali", "toma", "amra", "tui", "ahaan"],
    "urdu": ["urdu", "asalamoalaikoum", "sahib", "shukria"],
    "english": ["english", "the", "and", "is", "it", "hello", "thanks", "please"],
    "japanese": ["japanese", "arigatou", "sumimasen", "daijoubu", "wakarimasen", "watashi", "nihongo", "desu", "masu"],
}
TONE_KEYWORDS = {
    "authoritative": ["command", "order", "must", "required", "necessary", "authority", "insist"],
    "informal": ["hey", "hi", "hello", "yo", "sup", "hay", "hola"],
    "humorous": ["lol", "haha", "funny", "joke", "humor", "hilarious", "lmao"],
    "serious": ["seriously", "important", "matter", "crucial", "grave", "significant"],
    "empathetic": ["sorry", "understand", "feel", "empathy", "care", "support", "compassion"],
    "formal": ["formal", "sirs", "madam", "respect", "formally", "proper", "official"],
}
TONE_PRIORITY = ["authoritative", "serious", "empathetic", "humorous", "informal", "formal"]
MALE_HINTS = ["man", "men", "him", "his", "male", "guy", "dude", "brother", "bro", "boy"]
FEMALE_HINTS = ["woman", "women", "her", "hers", "female", "girl", "lady", "sister", "sis"]
YOUNG_HINTS = ["child", "kid", "boy", "girl", "young", "student", "junior", "childhood", "school"]
OLD_HINTS = ["elder", "old", "senior", "grandparent", "aged", "pensioner", "veteran"]
EMOTION_KEYWORDS = {
    "joy": ["happy", "joy", "glad", "pleased", "smile", "laugh", "happiness"],
    "sadness": ["sad", "sorry", "tears", "cry", "unhappy", "depressing", "melancholy"],
    "anger": ["angry", "mad", "furious", "rant", "aggressive", "enrage", "annoyed"],
    "fear": ["scared", "fear", "worried", "anxious", "terrified", "anxiety", "concerned"],
    "surprise": ["wow", "amazing", "surprise", "unexpected", "shock", "astonished"],
}
TONE_COMPAT = {
    "authoritative": {"authoritative": 20, "deep": 18, "commanding": 18, "resonant": 18, "epic": 16, "default": 5},
    "informal": {"conversational": 20, "natural": 18, "casual": 17, "friendly": 16, "youthful": 15, "default": 3},
    "humorous": {"melodic": 15, "energetic": 15, "warm": 12, "expressive": 14, "default": 2},
    "serious": {"authoritative": 20, "earnest": 18, "dramatic": 15, "resonant": 16, "default": 3},
    "empathetic": {"subtle": 18, "expressive": 17, "warm": 15, "gentle": 16, "nuanced": 17, "default": 3},
    "formal": {"sophisticated": 18, "elegant": 17, "polished": 15, "classic": 15, "default": 3},
    "neutral": {},
}
EMOTION_TONE = {
    "joy": {"energetic": 15, "melodic": 14, "happy": 13, "warm": 12, "default": 3},
    "sadness": {"subtle": 15, "gentle": 14, "melancholic": 13, "solemn": 11, "default": 2},
    "anger": {"authoritative": 15, "powerful": 14, "dramatic": 12, "intense": 10, "default": 2},
    "fear": {"nervous": 14, "worried": 13, "apprehensive": 11, "timid": 9, "default": 2},
    "surprise": {"expressive": 13, "animated": 12, "shocked": 10, "default": 2},
}

_actors: list | None = None
_PLACEHOLDER = re.compile(r"(?i)^(generic|name|test|actor|voice|sample|unknown|placeholder|tmp|temp)\d*$")


def _load() -> list:
    """Real, named actors only — the source database ships ~189 synthetic
    'Generic'/'Name' filler rows that would otherwise dominate English-language
    matches. The exclusion is reported by total_actors_excluded."""
    global _actors
    if _actors is None:
        all_actors = json.loads(DATA.read_text())["voiceActors"]
        _actors = [va for va in all_actors
                   if (va.get("name") or "").strip()
                   and not _PLACEHOLDER.match((va.get("name") or "").strip())]
    return _actors


def total_actors_excluded() -> int:
    return len(json.loads(DATA.read_text())["voiceActors"]) - len(_load())


def analyze_script(script: str) -> dict:
    """Faithful port of analyzeScript: language, tone, gender, age, emotions."""
    low = " " + re.sub(r"\s+", " ", str(script or "").lower()) + " "
    lines = [l for l in str(script or "").splitlines() if l.strip()]

    lang_scores = {}
    for lang, kws in LANGUAGE_MAP.items():
        score = sum(low.count(k) for k in kws)
        if lang in low:
            score += 5
        lang_scores[lang] = score
    ranked = sorted(lang_scores.items(), key=lambda kv: -kv[1])
    detected = [l for l, s in ranked if s > 0]

    tones = [t for t, kws in TONE_KEYWORDS.items() if any(k in low for k in kws)]
    tone = next((t for t in TONE_PRIORITY if t in tones), (tones[0] if tones else "neutral"))

    male = sum(low.count(k) for k in MALE_HINTS)
    female = sum(low.count(k) for k in FEMALE_HINTS)
    gender = "male" if male > female * 1.5 else "female" if female > male * 1.5 else None

    young = sum(low.count(k) for k in YOUNG_HINTS)
    old = sum(low.count(k) for k in OLD_HINTS)
    age = "young" if young > old and young > 0 else "senior" if old > young and old > 0 else "adult"

    emotions = [e for e, kws in EMOTION_KEYWORDS.items() if any(k in low for k in kws)]

    return {
        "language": (detected[0] if detected else "hindi").capitalize(),
        "secondaryLanguage": (detected[1].capitalize() if len(detected) > 1 else None),
        "allDetectedLanguages": [l.capitalize() for l in detected],
        "tone": tone,
        "genderPreference": gender,
        "ageRange": age,
        "emotionalContext": emotions,
        "characterCount": len(lines),
        "hasDialogue": len(lines) > 0,
    }


def _tone_match(script_tone: str, actor_tone: str) -> int:
    if not actor_tone:
        return 0
    low = actor_tone.lower()
    comp = TONE_COMPAT.get(script_tone.lower())
    if comp:
        for key, score in comp.items():
            if key != "default" and key in low:
                return score
        return comp["default"]
    return 2


def _emotion_match(emotions: list, actor_tone: str) -> float:
    if not actor_tone or not emotions:
        return 0.0
    low = actor_tone.lower()
    total, matched = 0.0, 0
    for e in emotions:
        data = EMOTION_TONE.get(e, {})
        hit = False
        for key, score in data.items():
            if key != "default" and key in low:
                total += score; matched += 1; hit = True
                break
        if not hit:
            total += data.get("default", 2); matched += 1
    return total / max(len(emotions), 1)


def _compatibility(f: dict, actor: dict) -> tuple[int, list[str]]:
    """Original scoring weights, with the reasons that produced them."""
    why = []
    score = 0
    ch = actor.get("voiceCharacteristics", {})
    langs = actor.get("languages", [])

    lang_score = 0
    if f["language"] in langs:
        lang_score = 30; why.append(f"dubs in {f['language']}")
    elif f["secondaryLanguage"] and f["secondaryLanguage"] in langs:
        lang_score = 20; why.append(f"secondary language {f['secondaryLanguage']}")
    score += lang_score

    if f["genderPreference"] and ch.get("gender") == f["genderPreference"]:
        score += 25; why.append(f"{ch.get('gender')} voice matches the cast")
    elif f["genderPreference"]:
        score += 0; why.append(f"gender note: {ch.get('gender')} voice")

    if f["ageRange"] == "young" and str(ch.get("ageRange", "")).lower() in ("young", "20-30", "teens"):
        score += 20; why.append("young-character range")
    elif f["ageRange"] == "senior" and str(ch.get("ageRange", "")).lower() in ("senior", "60-70", "50-60"):
        score += 20; why.append("senior-character range")
    else:
        score += 15; why.append(f"age range {ch.get('ageRange', '?')}")

    tm = _tone_match(f["tone"], ch.get("tone", ""))
    score += tm
    if tm >= 15:
        why.append(f"tone match: {ch.get('tone', '')}")

    em = _emotion_match(f["emotionalContext"], ch.get("tone", ""))
    score += em

    div = 0
    detected = f["allDetectedLanguages"] or [f["language"]]
    if detected and detected[0] in langs:
        div += 5
    if len(detected) > 1 and detected[1] in langs:
        div += 5
    matching = [l for l in langs if l in detected]
    if len(matching) >= 2 and len(langs) >= 2:
        div += 5
    elif len(matching) >= 1 and len(langs) >= 2:
        div += 3
    score += div
    if div >= 10:
        why.append(f"covers {len(matching)} of the script's languages")

    return min(int(score), 100), why


def cast_for_script(script: str, top_n: int = 5) -> dict:
    """Top voice-actor matches for a script. Deterministic, offline."""
    if not script or len(str(script).strip()) < 12:
        return {"status": "error", "error": "script text too short for casting analysis"}
    f = analyze_script(script)
    scored = []
    for actor in _load():
        score, why = _compatibility(f, actor)
        scored.append({
            "id": actor.get("id"),
            "name": actor.get("name"),
            "languages": actor.get("languages", []),
            "characteristics": actor.get("voiceCharacteristics", {}),
            "compatibility": score,
            "why": why[:3],
        })
    scored.sort(key=lambda m: -m["compatibility"])
    return {
        "status": "ok",
        "analysis": f,
        "best": scored[0] if scored else None,
        "recommendations": scored[:top_n],
        "total_actors": len(scored),
        "total_actors_excluded": total_actors_excluded(),
        "method": "port of voice-actor-system: language 30 · gender 25 · age 20 · tone 20 · emotion 15 · diversity 15 (0-100)",
    }


if __name__ == "__main__":
    out = cast_for_script("Aaj kal barish ho rahi hai. Main ghar ja raha hoon. Dhanyavad! "
                          "The young boy must command his fear and lead the village. Haha, what a journey.")
    print(json.dumps(out, indent=1, ensure_ascii=False)[:1600])
