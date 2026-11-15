"""Deterministic game engine for the Version 2 escape room.

Python owns the truth: state, rules and solutions live here and in
game_config.json. The LLM is only used (a) to turn free text into an intent
and (b) to narrate facts that the engine has already decided.
"""
import json
import re
from pathlib import Path

ACTIONS = {"examine", "search", "take", "use", "open", "enter_code",
           "inventory", "hint", "help", "meta", "unknown"}

# Messages that try to change the rules, claim authority or extract solutions.
META = re.compile(
    r"(ignore (all |any |the |your )?(previous|prior|above|earlier)|system prompt|"
    r"administrator|\badmin\b|game ?master mode|developer mode|debug mode|"
    r"reveal (all|every|the) (secret|code|solution|answer|hidden)|"
    r"(what|which) (is|are|'s) (the )?(secret|solution|answer|code)s?\b|"
    r"tell me (the )?(solution|answers?|codes?|secrets?)|\bjailbreak\b|"
    r"override|you are now|pretend (to be|you)|skip the puzzle|cheat)",
    re.I,
)


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def extract_code(message):
    """Digits are always extracted by Python, never trusted from the LLM."""
    m = re.search(r"(?<!\d)\d{3,4}(?!\d)", message or "")
    if m:
        return m.group(0)
    m = re.search(r"(?<!\d)(?:\d[\s\-,]+){2,3}\d(?!\d)", message or "")
    if m:
        return re.sub(r"\D", "", m.group(0))
    return None


class Game:
    def __init__(self, config_path="game_config.json", config=None):
        if config is None:
            config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self.cfg = config
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self):
        c = self.cfg
        self.state = {
            "visible_objects": [o for o, d in c["objects"].items() if d.get("visible", True)],
            "item_status": {i: "hidden" for i in c["items"]},  # hidden | available | inventory
            "inventory": [],
            "unlocked": [],
            "revealed_secrets": [],
            "searched": [],
            "attempts": {},
            "escaped": False,
            "turns": 0,
        }

    def name_of(self, kind, id_):
        table = self.cfg["objects"] if kind == "object" else self.cfg["items"]
        return table[id_]["name"]

    def inventory_names(self):
        return [self.name_of("item", i) for i in self.state["inventory"]]

    def solved_puzzles(self):
        return [o for o in self.state["unlocked"]]

    # -------------------------------------------------------------- resolving
    def mentions(self, text):
        """Return [(kind, id)] for objects/items mentioned in text, in order."""
        text = _norm(text)
        found = []
        for kind, table in (("object", self.cfg["objects"]), ("item", self.cfg["items"])):
            for id_, d in table.items():
                for alias in d["aliases"]:
                    for m in re.finditer(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", text):
                        found.append((m.start(), m.end(), kind, id_))
        found.sort(key=lambda t: -(t[1] - t[0]))  # prefer longer aliases
        accepted = []
        for s, e, k, i in found:
            if all(e <= s2 or s >= e2 for s2, e2, _, _ in accepted):
                accepted.append((s, e, k, i))
        accepted.sort()
        return [(k, i) for _, _, k, i in accepted]

    def resolve(self, text, kind):
        for k, i in self.mentions(text or ""):
            if k == kind:
                return i
        return None

    # ----------------------------------------------------------------- engine
    def _reveal(self, spec, facts):
        for o in spec.get("reveal_objects", []):
            if o not in self.state["visible_objects"]:
                self.state["visible_objects"].append(o)
        for i in spec.get("reveal_items", []):
            if self.state["item_status"][i] == "hidden":
                self.state["item_status"][i] = "available"

    def _visible(self, obj):
        return obj in self.state["visible_objects"]

    def apply(self, intent):
        """Validate and execute an intent dict. Returns {'ok', 'facts', ...}."""
        st = self.state
        action = intent.get("action", "unknown")
        target, item, code = intent.get("target"), intent.get("item"), intent.get("code")
        res = {"ok": False, "facts": [], "action": action}
        facts = res["facts"]

        if st["escaped"]:
            facts.append("The game is over: you have already escaped. Press Restart to play again.")
            return res
        st["turns"] += 1

        if action == "meta":
            facts.append("That is not something you can do from inside the room. "
                         "The rules of the game cannot be changed and nothing is handed to you. "
                         "You have to find the way out yourself.")
        elif action == "help":
            facts.append(self.cfg["help"]); res["ok"] = True
        elif action == "inventory":
            names = self.inventory_names()
            facts.append("You are carrying: " + ", ".join(names) + "." if names
                         else "Your pockets are empty.")
            res["ok"] = True
        elif action == "hint":
            facts.append(self._hint()); res["ok"] = True
        elif action in ("examine", "open"):
            self._examine(action, target, item, res)
        elif action == "search":
            self._search(target, res)
        elif action == "take":
            self._take(target, item, res)
        elif action == "use":
            self._use(target, item, res)
        elif action == "enter_code":
            self._enter_code(target, code, res)
        else:
            facts.append("You are not sure how to do that. Try examining something, taking an item, "
                         "using an item on something, or trying a code on a lock.")

        self._track_secrets(" ".join(facts))
        return res

    # --- handlers
    def _examine(self, action, target, item, res):
        st, facts = self.state, res["facts"]
        if target is None and item is not None:
            if st["item_status"][item] in ("available", "inventory"):
                facts.append(self.cfg["items"][item]["description"]); res["ok"] = True
            else:
                facts.append("You don't see anything like that here.")
            return
        if target is None:
            facts.append("What would you like to look at? The room contains things worth examining.")
            return
        if not self._visible(target):
            facts.append("You don't see anything like that here.")
            return
        obj = self.cfg["objects"][target]
        lock = obj.get("lock")
        if lock and target not in st["unlocked"]:
            facts.append(lock["locked_text"] if action == "open" else obj["examine"])
            if action == "open":
                res["ok"] = False
                return
        elif lock and target in st["unlocked"]:
            facts.append(obj.get("unlocked_examine", obj["examine"]))
        else:
            facts.append(obj["examine"])
        res["ok"] = True
        before = (list(st["visible_objects"]), dict(st["item_status"]))
        self._reveal(obj.get("on_examine", {}), facts)
        # mention newly available items so the player knows what can be taken
        for i, s in st["item_status"].items():
            if s == "available" and before[1][i] == "hidden":
                facts.append(f"You could take the {self.name_of('item', i)}.")

    def _search(self, target, res):
        st, facts = self.state, res["facts"]
        if target is None or not self._visible(target):
            facts.append("You search around but find nothing of interest." if target is None
                         else "You don't see anything like that here.")
            return
        spec = self.cfg["objects"][target].get("on_search")
        if not spec:
            facts.append(f"You search the {self.name_of('object', target)} carefully but find nothing new.")
            res["ok"] = True
            return
        if target in st["searched"]:
            facts.append(spec["empty_text"])
        else:
            st["searched"].append(target)
            facts.append(spec["text"])
            self._reveal(spec, facts)
        res["ok"] = True

    def _take(self, target, item, res):
        st, facts = self.state, res["facts"]
        if item is None:
            if target is not None and self._visible(target):
                facts.append(f"You cannot pick up the {self.name_of('object', target)}.")
            else:
                facts.append("You don't see anything like that here.")
            return
        status = st["item_status"][item]
        name = self.name_of("item", item)
        if status == "inventory":
            facts.append(f"You already have the {name}.")
        elif status == "available":
            st["item_status"][item] = "inventory"
            st["inventory"].append(item)
            facts.append(f"You take the {name}. {self.cfg['items'][item]['description']}")
            res["ok"] = True
        else:
            facts.append("You don't see anything like that here.")

    def _unlock(self, target, res):
        st, facts = self.state, res["facts"]
        lock = self.cfg["objects"][target]["lock"]
        st["unlocked"].append(target)
        facts.append(lock["unlock_text"])
        self._reveal(lock, facts)
        for i in lock.get("reveal_items", []):
            facts.append(f"You could take the {self.name_of('item', i)}.")
        if lock.get("win"):
            st["escaped"] = True
        res["ok"] = True

    def _use(self, target, item, res):
        st, facts = self.state, res["facts"]
        if item is None:
            facts.append("What do you want to use? Name an item you are carrying.")
            return
        if item not in st["inventory"]:
            facts.append("You are not carrying that, so you cannot use it.")
            return
        item_name = self.name_of("item", item)
        if target is None:
            facts.append(f"Use the {item_name} on what?")
            return
        if not self._visible(target):
            facts.append("You don't see anything like that here.")
            return
        lock = self.cfg["objects"][target].get("lock")
        tname = self.name_of("object", target)
        if lock and target in st["unlocked"]:
            facts.append(f"The {tname} is already unlocked.")
        elif lock and lock["type"] == "item":
            if lock["item"] == item:
                self._unlock(target, res)
            else:
                facts.append(lock["wrong_text"])
        else:
            facts.append(f"Nothing happens when you use the {item_name} on the {tname}.")

    def _enter_code(self, target, code, res):
        st, facts = self.state, res["facts"]
        if not code:
            facts.append("Which code do you want to try?")
            return
        if target is None:
            cands = [o for o in st["visible_objects"]
                     if self.cfg["objects"][o].get("lock", {}).get("type") == "code"
                     and o not in st["unlocked"]
                     and len(self.cfg["objects"][o]["lock"]["solution"]) == len(code)]
            if len(cands) != 1:
                facts.append("Which lock do you want to try that code on?")
                return
            target = cands[0]
        if not self._visible(target):
            facts.append("You don't see anything like that here.")
            return
        lock = self.cfg["objects"][target].get("lock")
        tname = self.name_of("object", target)
        if not lock or lock["type"] != "code":
            facts.append(f"The {tname} has no keypad or combination to enter a code on.")
            return
        if target in st["unlocked"]:
            facts.append(f"The {tname} is already unlocked.")
            return
        st["attempts"][target] = st["attempts"].get(target, 0) + 1
        if code == lock["solution"]:
            self._unlock(target, res)
        else:
            facts.append(lock["wrong_text"])

    # --- hints and secrets
    def _hint(self):
        st = self.state
        inv, vis, unl = st["inventory"], st["visible_objects"], st["unlocked"]
        status = st["item_status"]
        conds = {
            "note_hidden": status["note"] == "hidden",
            "books_hidden": "books" not in vis,
            "drawer_locked": "drawer" not in unl,
            "key_not_taken": "brass_key" not in inv,
            "safe_hidden": "wall_safe" not in vis,
            "safe_locked": "wall_safe" not in unl,
            "paper_not_taken": "paper" not in inv,
            "ready": True,
        }
        for h in self.cfg["hints"]:
            if conds[h["when"]]:
                return h["text"]
        return "Keep exploring."

    def _track_secrets(self, text):
        compact = text
        for s in self.cfg.get("secrets", []):
            if re.search(_digit_pattern(s), compact) and s not in self.state["revealed_secrets"]:
                self.state["revealed_secrets"].append(s)


def _digit_pattern(s):
    return r"(?<!\d)" + r"[\s,.\-]*".join(s) + r"(?!\d)"


# --------------------------------------------------------------------- parsing
def rule_parse(game, message):
    """Keyword intent parser. Used when no LLM is available or it misbehaves."""
    t = _norm(message)
    ments = game.mentions(t)
    objs = [i for k, i in ments if k == "object"]
    items = [i for k, i in ments if k == "item"]
    code = extract_code(message)

    def has(*pats):
        return any(re.search(p, t) for p in pats)

    if META.search(t):
        action = "meta"
    elif has(r"\binventory\b", r"\bpockets?\b", r"what (do i|am i) (have|carrying|holding)"):
        action = "inventory"
    elif has(r"\bhints?\b", r"\bstuck\b", r"help me"):
        action = "hint"
    elif has(r"\bhelp\b", r"instructions", r"how (do i|to) play", r"\bcommands\b"):
        action = "help"
    elif code and not has(r"\btake\b", r"\bgrab\b"):
        action = "enter_code"
    elif has(r"\btake\b", r"\bgrab\b", r"pick up", r"\bcollect\b", r"\bpocket\b", r"\bget\b"):
        action = "take"
    elif has(r"\buse\b", r"\binsert\b", r"\bapply\b", r"\bunlock\b.*\bwith\b") or \
            (has(r"\b(open|unlock)\b") and items):
        action = "use"
    elif has(r"\bsearch\b", r"behind", r"\bmove\b", r"\blift\b", r"\bpush\b", r"\bpull\b",
             r"\bswing\b", r"\bslide\b", r"\bpeek\b", r"\bshift\b"):
        action = "search"
    elif has(r"\bopen\b", r"\bunlock\b"):
        action = "open"
    elif has(r"\bexamine\b", r"\blook\b", r"\binspect\b", r"\bcheck\b", r"\bread\b",
             r"\bstudy\b", r"\binvestigate\b", r"\bsee\b", r"\bview\b", r"\bdescribe\b"):
        action = "examine"
    elif ments:
        action = "examine"
    else:
        action = "unknown"
    return {"action": action, "target": objs[0] if objs else None,
            "item": items[0] if items else None, "code": code if action == "enter_code" else None,
            "source": "rules"}


def sanitize_intent(game, raw, message):
    """Turn untrusted LLM JSON into a validated intent. Python extracts code & resolves names."""
    raw = raw if isinstance(raw, dict) else {}
    action = str(raw.get("action", "unknown")).lower().strip()
    if action not in ACTIONS:
        action = "unknown"
    if META.search(message or ""):
        action = "meta"
    code = extract_code(message)
    if action == "enter_code" and not code:
        action = "unknown"
    return {"action": action,
            "target": game.resolve(str(raw.get("target_text") or ""), "object"),
            "item": game.resolve(str(raw.get("item_text") or ""), "item"),
            "code": code if action == "enter_code" else None,
            "source": "llm"}


def leaks(game, text, user_message=""):
    """True if a narration reveals something the engine has not revealed yet."""
    for s in game.cfg.get("secrets", []):
        if s in game.state["revealed_secrets"] or s in (user_message or ""):
            continue
        if re.search(_digit_pattern(s), text):
            return True
    st = game.state
    for o, d in game.cfg["objects"].items():
        if o not in st["visible_objects"] and re.search(
                r"(?<![a-z])" + re.escape(d["name"]) + r"(?![a-z])", text.lower()):
            return True
    for i, d in game.cfg["items"].items():
        if st["item_status"][i] == "hidden" and re.search(
                r"(?<![a-z])" + re.escape(d["name"]) + r"(?![a-z])", text.lower()):
            return True
    return False


def take_turn(game, message, llm=None):
    """One full turn: parse -> validate/apply -> narrate -> leak check."""
    message = (message or "").strip()[:500]
    if not message:
        return {"reply": "Say what you would like to do.", "intent": None, "narrated": False}
    intent = None
    if llm is not None:
        try:
            intent = sanitize_intent(game, llm.parse(message), message)
            if intent["action"] == "unknown":
                intent = None
        except Exception:
            intent = None
    if intent is None:
        intent = rule_parse(game, message)
    result = game.apply(intent)
    reply, narrated = " ".join(result["facts"]), False
    if llm is not None and result["facts"]:
        try:
            text = llm.narrate(result["facts"], message)
            if text and not leaks(game, text, message):
                reply, narrated = text.strip(), True
        except Exception:
            pass
    return {"reply": reply, "intent": intent, "result": result, "narrated": narrated}
