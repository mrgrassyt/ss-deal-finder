"""Text analysis for listings: normalisation, condition, bundle / lot / risk flags
and fingerprints for repost detection. Handles Latvian, Russian and English."""
from __future__ import annotations

import functools
import hashlib
import re
import unicodedata

LV_FOLD = str.maketrans("āčēģīķļņšūžĀČĒĢĪĶĻŅŠŪŽ", "acegiklnsuzACEGIKLNSUZ")


def fold(text: str) -> str:
    """Lowercase + strip Latvian diacritics so 'bojāts' and 'bojats' match."""
    t = (text or "").lower().translate(LV_FOLD)
    t = unicodedata.normalize("NFKC", t)
    return t


def norm(text: str) -> str:
    t = fold(text)
    t = re.sub(r"(\d)\s*(?:\"|”|″|''|“|collu|colli|coll|дюйм\w*)", r"\1 inch", t)
    t = re.sub(r"[“”\"'`´]", "", t)
    t = re.sub(r"[_|*~•·]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


@functools.lru_cache(maxsize=4096)
def _compiled(pattern: str) -> re.Pattern:
    # patterns are folded the same way as the text so diacritics never matter
    return re.compile(fold(pattern))


def has(t: str, pattern: str) -> bool:
    return _compiled(pattern).search(t) is not None


# ---------------------------------------------------------------- condition

NEGATED_DAMAGE = (
    r"bez (?:jebkadiem |nekadiem )?(?:bojajum\w*|defekt\w*|problem\w*|skrapejum\w*)",
    r"nav (?:nekadu |nevienu )?(?:bojajum\w*|defekt\w*|problem\w*)",
    r"nekadu (?:bojajum\w*|defekt\w*|problem\w*)",
    r"nav bojats", r"nav saluzis", r"nav remontets", r"nav bijis remonta", r"nekad nav remontets",
    r"без (?:каких-либо )?(?:дефект\w*|повреждени\w*|проблем\w*)", r"не ремонтировал\w*",
    r"no (?:issues|problems|defects|damage)", r"not broken", r"never repaired",
)

BROKEN_PATTERNS = (
    r"nestrada", r"\bneiet\b", r"neieslēdzas", r"neiesledzas", r"neielade", r"bojat", r"bojaj",
    r"saluz", r"saplis", r"plis\w* ekran", r"sasist", r"defekt", r"nav attela", r"nav bildes",
    r"artefakt", r"remontam", r"nepieciesams remonts", r"vajag remont", r"jaremonte",
    r"not working", r"\bbroken\b", r"faulty", r"\bdead\b", r"cracked", r"no display", r"no signal",
    r"не работает", r"неисправ", r"сломан", r"разбит", r"треснут", r"нет изображения", r"не включается",
    r"требует ремонт", r"артефакт",
)
PARTS_PATTERNS = (
    r"uz detal", r"rezerves dal\w*(?: (?:veida|nolukiem))?(?![a-z])", r"detalam", r"for parts", r"parts only",
    r"на запчасти", r"на детали", r"donor", r"donors",
)
UNTESTED_PATTERNS = (
    r"neparbaud", r"nav parbaud", r"netestet", r"nav testet", r"nav zinams vai strada", r"nezinu vai strada",
    r"untested", r"not tested", r"unknown condition", r"не проверял", r"не проверен", r"не тестировал",
)
NEW_PATTERNS = (
    r"\bjaun[saie]?\b(?! ka)", r"neizpakot", r"neatverts", r"neatvert", r"oriģinal\w* iepakojum\w* neatvert",
    r"\bsealed\b", r"brand new", r"\bnew in box\b", r"\bnib\b", r"новый", r"новая", r"нераспакован", r"запечатан",
)
LIKE_NEW_PATTERNS = (r"\bka jaun", r"like new", r"как новый", r"ideal\w* stavokl", r"perfekt\w* stavokl",
                     r"lieliska stavokli", r"teicam\w* stavokl", r"отличн\w* состояни")


# "selling it in parts / for parts": the whole device, not working or being parted out (Latvian locative "daļās/daļām"
# is checked before accents are removed, because "rezerves daļas" alone also means "spare parts" = a part for sale)
WHOLE_FOR_PARTS = re.compile(r"(?:rezerves|uz)\s+daļ(?:ās|ām)|uz\s+detaļām|по\s+запчастям|на\s+(?:запчасти|детали|донор)|"
                             r"\bfor\s+parts\b|\bas\s+parts\b|\bparts\s+only\b|\bdonor\b|\bdonors\b", re.I)


def sold_whole_for_parts(text: str) -> bool:
    return bool(WHOLE_FOR_PARTS.search((text or "").lower()))


def detect_condition(text: str, attrs: dict | None = None) -> tuple[str, list[str]]:
    """Returns (condition, evidence). condition ∈ new|used|broken|parts|untested."""
    if sold_whole_for_parts(text):
        return "parts", ["sold for parts"]
    t = norm(text)
    for neg in NEGATED_DAMAGE:
        t = _compiled(neg).sub(" ", t)
    evidence: list[str] = []
    attr_cond = ""
    for k, v in (attrs or {}).items():
        if fold(k).startswith(("stavoklis", "состояние")):
            attr_cond = fold(v)
    for p in PARTS_PATTERNS:
        if has(t, p):
            evidence.append(f"parts: '{p}'")
            return "parts", evidence
    for p in BROKEN_PATTERNS:
        if has(t, p):
            evidence.append(f"broken: '{p}'")
            return "broken", evidence
    for p in UNTESTED_PATTERNS:
        if has(t, p):
            evidence.append(f"untested: '{p}'")
            return "untested", evidence
    if attr_cond.startswith(("jaun", "нов", "new")):
        return "new", ["attribute: new"]
    if attr_cond.startswith(("liet", "б/у", "used")):
        if any(has(t, p) for p in LIKE_NEW_PATTERNS):
            return "used", ["attribute: used", "like new wording"]
        return "used", ["attribute: used"]
    for p in LIKE_NEW_PATTERNS:
        if has(t, p):
            return "used", ["like new wording"]
    for p in NEW_PATTERNS:
        if has(t, p):
            return "new", [f"new: '{p}'"]
    return "used", ["default"]


# ---------------------------------------------------------------- flags

FLAG_PATTERNS = {
    "bundle": (r"\bkomplekt", r"\bkit\b", r"ar objektiv", r"\+ ?objektiv", r"\bbundle\b", r"\bkomplektā",
               r"комплект", r"в комплекте", r"\+ ?2 ?(?:speles|speli|kontrolier)", r"ar (?:spelem|kontrolier)",
               r"together with", r"\+ ?(?:lens|objektivs|akumulator|ladetaj|soma|statīv|statīvs)"),
    "collection": (r"\bkaste ar\b", r"\bdazadi\b", r"\bdazadas\b", r"\bkolekcij", r"\bpartija", r"\bvairum",
                   r"\blots?\b", r"\bjob lot", r"\bnaborins", r"\bmaiss ar", r"\bkudi?ns\b", r"набор",
                   r"коробка с", r"разное", r"\bvisi kopa\b", r"\bkopa par\b", r"\d+ ?gab\.? ", r"\bx ?\d{1,2} ?gab"),
    "warranty": (r"garantij", r"гаранти", r"warranty"),
    "receipt": (r"\bceks\b", r"\bcekis\b", r"pirkuma dokument", r"чек", r"receipt"),
    "box": (r"oriģinal\w* (?:kaste|iepakojum)", r"originala (?:kaste|iepakojum)", r"\bkaste\b", r"iepakojum",
            r"коробк", r"\bbox\b"),
    "mining": (r"majning", r"mining", r"майнинг", r"\bmain(?:eja|ets)\b", r"kriptovalut"),
    "exchange": (r"\bmaina\b", r"\bmainai\b", r"maina pret", r"обмен", r"меняю", r"\bswap\b", r"\btrade\b"),
    "urgent": (r"steidzami", r"steidzigi", r"срочно", r"urgent", r"atrā pārdošana", r"atra pardosana"),
    "negotiable": (r"iespejama atlaide", r"\bkaulēties\b", r"kaulet", r"torg", r"торг", r"negotiable", r"\bobo\b"),
    "shipping": (r"pakomat", r"omniva", r"dpd", r"sutu", r"nosutu", r"varu nosutit", r"отправлю", r"shipping"),
    "shop": (r"\bveikal\w*\b.*(?:piedavaj|sortiment)", r"piedavajam", r"musu veikal", r"\bsia\b", r"pvn", r"rēķin",
             r"rekin", r"interneta veikal", r"магазин", r"предлагаем"),
}
BUYING_PATTERNS = (r"^\s*perku", r"\bperku\b", r"\bnopirksu\b", r"\bmekleju\b", r"^\s*куплю", r"\bкуплю\b",
                   r"\bищу\b", r"\bwant to buy\b", r"\bwtb\b")
SERVICE_PATTERNS = (r"\bremontejam\b", r"\bremonts\b.*\b(?:cena|no)\b", r"piedavaju pakalpojum", r"\bpakalpojum",
                    r"\bnoma\b", r"\bnomai\b", r"\bizirē", r"izire", r"fotografs", r"fotosesij", r"ремонт компьютер",
                    r"аренда", r"услуг", r"\bdatoru remont", r"\btelefonu remont", r"programmatur\w* instal",
                    # repair / replacement offered as a job: "ekrāna nomaiņa", "замена экрана", "ремонт телефонов"
                    r"\b(?:ekran\w*|akumulator\w*|displej\w*|stikl\w*) nomaina\b", r"\bnomaina (?:ekran|akumulator|displej|stikl)",
                    r"замен\w* (?:экран|аккумулятор|дисплей|стекл|батаре)", r"ремонт\w* (?:телефон|ноутбук|компьютер|планшет|iphone|техник)",
                    r"\bveicu (?:remont|diagnost|uzstad|tirisan)", r"\bsniedzu\b", r"\bremontu\b.*\b(?:telefon|dator|planset|iphone|samsung)",
                    r"\b(?:telefonu|planšetu|datoru|iphone|macbook)\s*remonts\b", r"\bdiagnostika\b.*\bbezmaksas",
                    r"\buzstadisana\b", r"\bdatu atgusana\b", r"\bprogrammatura\b.*\buzstad", r"\bizirēju\b")


# A repair SHOP describes what it does, an item ad says what is for sale. Count both, read the whole text.
SERVICE_SIGNALS = (
    r"\bremont\w*", r"\bservis\w*", r"atbloke?san\w*|atslegsan\w*|atblokej\w*|разблокир\w*", r"izbrauk\w*|izbraucam|pie klienta|выезд",
    r"aizsargstikl\w*", r"mes (?:busim|varam|piedavajam|veicam|sniedzam|remontejam)", r"priecig\w* palidzet|\bpalidzet\b",
    r"diagnost\w*", r"nomain\w* (?:ekran|akumulator|displej|stikl|port)|(?:ekran|akumulator|displej|stikl)\w* nomain\w*",
    r"atri un kvalitat|kvalitat\w* (?:remont|serv)|bez rindas|visu veidu|visiem modeliem", r"garantija uz (?:remont|darb|detal)",
    r"darba laiks|pienemam|pieteikt\w*|rezervet\w* laiku|bezmaksas konsultacij",
    r"\bidoctor\b|\bservisa centr\w*", r"(?:apple|iphone|ipad|samsung|huawei|xiaomi)[ ,]+(?:apple|iphone|ipad|samsung|huawei|xiaomi)[ ,]+(?:apple|iphone|ipad|samsung|huawei|xiaomi|lg|sony|oppo)",
)
ITEM_SALE_SIGNALS = (SALE_VERBS_RX := r"(?:pardodu|pardod|продаю|продам|selling|for sale)", r"\bstavokli\b", r"\bimei\b", r"(?:akumulator|baterij)\w* kapacitate",
                     r"\bar kasti\b|\bkaste\b ir", r"\blietots (?:telefons|planset|iphone|ipad|macbook)", r"\bpilnaa? komplekt")
NEEDS_REPAIR_ITEM = (r"bojat\w*", r"uz detalam", r"uz zapcastem", r"vajag remont\w*", r"vajadzig\w* remont\w*", r"nestrada", r"neieslegas", r"на запчасти", r"требует ремонт", r"нужен ремонт")


def service_verdict(text: str) -> tuple[bool, str]:
    """(is_service, reason) from the full ad text. A device that is for sale and 'needs repair' is still an item."""
    t = norm(text)
    signals = [p for p in SERVICE_SIGNALS if re.search(p, t)]
    if not signals:
        return False, ""
    sale = [p for p in ITEM_SALE_SIGNALS if re.search(p, t)]
    sale_verb = bool(re.search(ITEM_SALE_SIGNALS[0], t))
    if sale_verb and any(re.search(p, t) for p in NEEDS_REPAIR_ITEM):
        return False, "device for sale that needs repair: still an item"
    if len(signals) >= 2 and not sale:
        return True, f"reads like a repair/service offer ({len(signals)} service phrases, nothing for sale)"
    if len(signals) >= 4 and not sale_verb:
        return True, f"many service phrases ({len(signals)}) and no sale wording"
    return False, ""


def detect_flags(text: str) -> list[str]:
    t = norm(text)
    flags = [name for name, pats in FLAG_PATTERNS.items() if any(has(t, p) for p in pats)]
    if any(has(t, p) for p in BUYING_PATTERNS):
        flags.append("buying")
    if any(has(t, p) for p in SERVICE_PATTERNS) or service_verdict(text)[0]:
        flags.append("service")
    return flags


# ---------------------------------------------------------------- junk accessories

LOW_VALUE_ITEMS = (
    r"\bladetaj", r"\bkabel", r"\bvads\b", r"\bvadi\b", r"\bpults?\b", r"\bmacin", r"\bvacin", r"\bvaks",
    r"aizsargstikl", r"aizsargplev", r"\bsiksn", r"\bplevit", r"\badapter", r"\bmaciņš", r"\bsoma\b",
    r"\bcase\b", r"\bcover\b", r"\bcharger\b", r"\bcable\b", r"чехол", r"кабель", r"заряд", r"пульт", r"плёнк",
    r"\bpeles paklaj", r"mouse ?pad", r"\bdisketes?\b", r"\bkasetes?\b", r"\bcd diski\b", r"\bdvd diski\b",
)


def is_low_value_item(text: str) -> bool:
    t = norm(text[:200])
    return any(has(t, p) for p in LOW_VALUE_ITEMS)


# ---------------------------------------------------------------- fingerprints

def fingerprint(text: str) -> str:
    t = norm(text)
    t = re.sub(r"\d+[.,]?\d*\s*(eur|€)", " ", t)       # strip prices so a repost at a new price matches
    t = re.sub(r"(?:\+?371)?\s?\d{8}", " ", t)          # phone numbers
    t = re.sub(r"[^a-z0-9а-я ]+", " ", t)
    words = [w for w in t.split() if len(w) > 2][:40]
    h = hashlib.sha1(" ".join(words).encode()).hexdigest()[:16]
    # short texts (titles) collide between different sellers: mark them as weak
    return h if len(words) >= 8 else "t:" + h


def tokens(text: str) -> set[str]:
    t = re.sub(r"[^a-z0-9а-я ]+", " ", norm(text))
    return {w for w in t.split() if len(w) > 2 and not w.isdigit()}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------- part / accessory vs the device itself
# "Selling a new iPhone 13 battery" must not be valued as an iPhone 13, and it must not pollute the iPhone 13 market.
# Only the *head* of the sentence decides: "ar jaunu akumulatoru" (with a new battery) describes a whole device.

PART_WORDS = (
    r"akumulator\w*", r"baterij\w*", r"bateri\w*", r"batarejk\w*", r"аккумулятор\w*", r"акумулятор\w*", r"батаре\w*", r"battery", r"batteries",
    r"ekran\w*", r"displej\w*", r"дисплей\w*", r"экран\w*", r"screens?", r"displays?", r"lcd",
    r"matesplat\w*", r"motherboards?", r"материнск\w+ плат\w*", r"kameras? modul\w*", r"camera modules?",
    r"flekss?", r"шлейф\w*", r"aizmugurej\w* (?:vak|stikl|panel)\w*", r"back (?:glass|cover|housing)", r"крышк\w* (?:задн|корпус)\w*",
    r"korpus\w*", r"housing", r"матриц\w*", r"matric\w*", r"клавиатур\w* для", r"tastatur\w* priekš", r"rezerves dal\w*", r"запчаст\w*", r"spare parts?",
)
ACCESSORY_WORDS = (
    r"apvalk\w*", r"vaci\w*", r"macin\w*", r"чехл\w*", r"бампер\w*", r"cases?", r"covers?", r"bumpers?",
    r"aizsargstikl\w*", r"aizsargplev\w*", r"aizsargpl\w*", r"защитн\w* (?:стекл|плёнк|пленк)\w*", r"screen protectors?", r"tempered glass",
    r"ladetaj\w*", r"зарядк\w*", r"зарядн\w*", r"chargers?", r"kabel\w*", r"кабел\w*", r"cables?", r"adapter\w*", r"адаптер\w*",
    r"siksn\w*", r"ремеш\w*", r"straps?", r"watch bands?", r"turetaj\w*", r"держател\w*", r"holders?",
    # console / PC gaming gear and software: sold FOR a console, not a console
    r"controllers?", r"gamepads?", r"joysticks?", r"dualsense", r"dualshock", r"pult\w*", r"spelu pult\w*", r"геймпад\w*", r"джойстик\w*", r"пульт\w*",
    r"steering wheels?", r"racing wheels?", r"sture\w*", r"руль\w*", r"wheels?", r"headsets?", r"ausinas", r"austin\w*", r"наушник\w*",
    r"spele\w*", r"games?", r"игр\w*", r"disks?", r"discs?", r"диск\w*", r"memory cards?", r"charging (?:dock|station)", r"dock\w*", r"dokstacij\w*", r"uzlades stacij\w*", r"lades stacij\w*", r"док-?станц\w*", r"зарядн\w* станц\w*",
)
# gaming peripherals recognised ANYWHERE in the headline ("Logitech G29 stūre PS5/PC"), unless the ad is clearly a console
GAMING_ACCESSORY = r"(?:ssd|hdd|m\.?2|heatsink|dzesetaj\w*|kontrolier\w*|joy-?cons?|apvalk\w*|vaks|stends|ventilator\w*|dzesesanas|cooling|kamera|atminas kart\w*|memory cards?|hdmi|kabel\w*|cables?|logitech|thrustmaster|fanatec|g29|g920|g923|t300|t150|dualsense|dualshock|controllers?|gamepads?|pult\w*|sture\w*|steering|racing wheel|joystick|geймпад|геймпад\w*|руль\w*|headsets?|spelu stur\w*|spele\w*|games?|игр\w*)"
CONSOLE_NOUN = r"(?:konsol\w*|console|приставк\w*|playstation ?[345] (?:slim|pro|digital)|ps[345] (?:slim|pro|digital)|xbox series [sx]|xbox one (?:s|x)|switch (?:oled|lite))"
DEVICE_FULL = {"telefons", "telefonu", "talrunis", "talruni", "smartfons", "smartfonu", "viedtalrunis", "viedtalruni", "phone", "smartphone",
               "телефон", "смартфон", "планшет", "planset", "planšet", "tablet", "laptop", "dators", "datoru", "pulkstenis", "pulksteni", "watch", "часы"}
SALE_VERBS = r"(?:pardodu|pardod|piedavaju|продаю|продам|selling|sell|for sale|pārdodu)"
STOP_BETWEEN = {"ar", "with", "с", "со", "и", "un", "+", "bez", "без", "and", "plus", "ieskaitot", "kopa"}
DAMAGE_AFTER = (r"bojat", r"saplis", r"plis", r"cracked", r"broken", r"разбит", r"треснут", r"nestrada", r"not working", r"не работает")
FOR_WORDS = r"(?:priekš\w*|priekš|paredz\w*|piemerot\w*|saderig\w*|for|compatible with|для|под|совместим\w*)"
KIND_CATEGORIES = {"peripheral", "phone", "tablet", "wearable", "laptop", "console", "drone", "camera", "other", "smart_home", "pc_parts_other"}


def _first_sentence(text: str, n: int = 220) -> str:
    t = norm(text or "")
    m = re.split(r"[.!?\n]", t, maxsplit=1)
    return (m[0] if m else t)[:n]


def _alt(words: tuple) -> str:
    return "(?:" + "|".join(fold(w) for w in words) + ")"


GAME_TITLES = (r"fifa|ea sports fc|ea fc|\bgta\b|grand theft auto|call of duty|\bcod\b|spider-?man|god of war|last of us|horizon (?:zero|forbidden)|gran turismo|mortal kombat|elden ring|"
               r"fortnite|minecraft|assassin.?s creed|far cry|resident evil|cyberpunk|ghost of (?:tsushima|yotei)|ratchet|returnal|astro bot|nba 2k|wwe 2k|uncharted|hogwarts legacy|"
               r"tekken|street fighter|battlefield|need for speed|forza|\bhalo\b|zelda|mario|pokemon|it takes two|red dead|witcher|dying light|rocket league|crash bandicoot|sackboy|"
               r"bloodborne|days gone|dead space|diablo|\blego\b|the crew|f1 ?2\d|moto ?gp|hitman|watch dogs|sniper elite|dragon ball|naruto|one piece|persona|final fantasy|kena|stray")
CONSOLE_NAME = r"(?:ps ?[2-5]|ps vita|playstation ?[2-5]?|xbox(?: series [sx]| one)?|nintendo switch|switch|steam deck)"
CONSOLE_HARDWARE = r"(?:konsol\w*|console|приставк\w*|digital edition|disc edition|komplekt\w*|kopa ar|\bar \d ?pult\w*|\d ?pults?|\d ?controllers?|garantij\w*|kaste\b)"
DRIVE_WORD = r"(?:ssd|hdd|nvme|m\.?2|cietais disks)"


def _console_ad_kind(title: str, description: str) -> str:
    """For ads that name a console: is it the console, or something sold FOR it (drive, games, accessory)?"""
    t, d = norm(title)[:140], norm(description)[:700]
    if not (re.search(CONSOLE_NAME, t) or re.search(CONSOLE_NAME, d[:300])):
        return ""
    first = _first_sentence(description or "")
    hardware_t = re.search(CONSOLE_HARDWARE, t)
    # sold "for" a console anywhere in the first lines of the description
    m = re.search(rf"\b{fold(FOR_WORDS)}\s+(?:\w+\s+){{0,2}}?{CONSOLE_NAME}", d[:300])
    if m and not re.search(CONSOLE_HARDWARE, d[:m.start()]) and not hardware_t:
        return "described as sold for a console, not a console"
    # a drive offered on its own: "Pārdodu SSD 1TB", "Crucial P5 Plus SSD 1TB, der PS5"
    if re.match(rf"^(?:{SALE_VERBS}\s+)?(?:\S+\s+){{0,4}}?{DRIVE_WORD}\b", first) and not re.search(r"\+|\bar\b|\bwith\b", first[:first.find("ssd") if "ssd" in first else 0]) \
            and not re.search(CONSOLE_HARDWARE, first) and not hardware_t:
        return "the ad offers a storage drive, not the console"
    if re.search(DRIVE_WORD, d[:200]) and re.search(r"(?:samsung\s*9\d0|wd[ _]?black|\bsn\d{3}|crucial|kingston|seagate|sabrent|firecuda|heatsink|dzesetaj)", d[:200]) \
            and not re.search(CONSOLE_HARDWARE, d[:300]) and not hardware_t:
        return "a named storage drive in the ad, no console hardware"
    # game lists: two or more game names, or one in the headline
    games = {g for g in re.findall(GAME_TITLES, f"{t} {d}")}
    if (len(games) >= 2 or re.search(GAME_TITLES, t)) and not re.search(CONSOLE_HARDWARE, d[:300]) and not hardware_t:
        return "a list of games, not a console"
    gm = re.match(rf"^(?:{SALE_VERBS}\s+)?((?:\S+\s+){{0,3}}?)(?:spele\w*|games?|disk\w*|diski)\b", first)
    if gm and not re.search(r"\bar\b|\bwith\b|\+|\bun\b|\bkopa\b", gm.group(1)) and not re.search(CONSOLE_HARDWARE, first) and not hardware_t:
        return "the ad offers games/discs, not a console"
    return ""


def detect_kind(title: str, description: str, category: str | None = None) -> tuple[str, str]:
    """Returns (kind, reason); kind is 'device', 'part' or 'accessory'."""
    if category and category not in KIND_CATEGORIES:
        return "device", ""
    parts_re, acc_re = _alt(PART_WORDS), _alt(ACCESSORY_WORDS)
    # "Pārdodu HP ProBook 450 G9 - pārdodu rezerves daļās": the laptop itself, broken or parted out, not one part
    if sold_whole_for_parts(f"{title}\n{description or ''}") and not re.search(rf"^(?:\S+\s+){{0,2}}(?:{parts_re}|{acc_re})", norm(title or "")):
        return "device", "whole device sold for parts"
    candidates = [norm(title or "")[:140], _first_sentence(description or "")]
    for kind, rx in (("accessory", acc_re), ("part", parts_re)):
        for text in candidates:
            if not text:
                continue
            # A) "Pārdodu jaunu iPhone 13 akumulatoru": sale verb, a few plain words, then the part – no comma/“with” in between
            m = re.search(rf"{SALE_VERBS}\s+((?:[^\s,.;:+()]+\s+){{0,5}}?)({rx})(?![\w])", text)
            if m:
                between = m.group(1).split()
                if not any(w in STOP_BETWEEN for w in between) and not any(w in DEVICE_FULL for w in between):
                    after = text[m.end():m.end() + 30]
                    if not any(re.search(d, after) for d in DAMAGE_AFTER):
                        return kind, f"sale text starts with a {kind}: '{m.group(2)}'"
            # B) a title that starts with the part: "Akumulators iPhone 13", "Screen Samsung A55", "Case for Galaxy S24"
            words = text.split()
            lead = " ".join(words[:4])
            m = re.match(rf"^(?:jaun\w*|origin\w*|oriģin\w*|original|new|used|lietot\w*|новый|новая|новые|оригинальный)?\s*({rx})(?![\w])", lead)
            if m and not any(re.search(d, text[m.end():m.end() + 25]) for d in DAMAGE_AFTER):
                return kind, f"title starts with a {kind}: '{m.group(1)}'"
            # B2) short title that ends with the accessory: "Samsung S24 case"
            mend = re.search(rf"(?:^|\s)({rx})$", " ".join(words)) if len(words) <= 7 else None
            if mend:
                head = " ".join(words)[:mend.start(1)]
                withy = "+" in head or any(re.search(rf"(?<![a-z]){w}(?![a-z])", head) for w in ("ar", "with", "с", "un", "and", "komplekta", "ieskaitot", "bez"))
                if not withy and not re.search(fold(CONSOLE_NOUN), text):
                    return kind, f"title ends with a {kind}"
            # B3) "<device name/model code> battery|screen ..." in a short headline, no "with/ar/+" before it
            if kind == "part" and len(words) <= 8:
                mm = re.search(rf"(?:^|\s)({rx})(?:\s|$)", " ".join(words))
                if mm:
                    head = " ".join(words)[:mm.start(1)]
                    if head.strip() and not ("+" in head or any(re.search(rf"(?<![a-z]){w}(?![a-z])", head) for w in ("ar", "with", "с", "un", "and", "komplekta", "ieskaitot", "bez"))) \
                            and not any(re.search(d, " ".join(words)[mm.end(1):]) for d in DAMAGE_AFTER) \
                            and not re.search(r"\b\d{2,3}\s*%", " ".join(words)):
                        return kind, f"headline names a device and a part: '{mm.group(1)}'"
            # C) "<part> for <device>" near the start
            m = re.search(rf"^[^,.;]{{0,40}}?\b({rx})\b[^,.;]{{0,25}}?\b{FOR_WORDS}\b", text)
            if m:
                return kind, f"'{m.group(1)} for …' wording"
    # the ad text, not just the headline: "PlayStation 5" + a description of an SSD / a list of games / "priekš PS5"
    if not category or category in ("console", "other", "peripheral", "pc_parts_other"):
        verdict = _console_ad_kind(title or "", description or "")
        if verdict:
            return "accessory", verdict
    # a console name followed straight by a storage product ("PS5 Slim SSD 1TB", "PS5 SSD Samsung 990 Pro heatsink"): the drive, not the console
    if not category or category in ("console", "other", "peripheral", "pc_parts_other"):
        for text in candidates[:1]:
            if not text:
                continue
            head = " ".join(text.split()[:9])
            console = r"(?:ps ?[2-5]|playstation ?[2-5]|xbox(?: series [sx]| one)?|steam deck|rog ally)(?: slim| pro| digital| disc)?"
            drive = r"(?:ssd|hdd|nvme|m\.?2)"
            brand = r"(?:samsung\s*9\d0|\b9[89]0\s*pro|wd[ _]?black|\bsn\d{3}x?\b|firecuda|crucial|kingston|seagate|sabrent|corsair mp\d+|heatsink|dzesetaj\w*)"
            plus = re.search(r"(?:\+|\bar\b|\bwith\b|\bkomplekt\w*|\bieskaitot\b)", head)
            if re.match(rf"^{console}\s+(?:(?!\d)\w+\s+){{0,1}}?{drive}\b", head) and not plus and not re.search(r"konsol|console|controller|kontrolier|spel|games?", head):
                return "accessory", "console name followed by a storage drive: the drive is for sale, not the console"
            if re.search(rf"{drive}\b", head) and re.search(brand, head) and re.search(console, head) and not plus \
                    and not re.search(r"konsol|console|digital|disc|diska", head):
                return "accessory", "named drive for a console, not a console"
    if not category or category in ("console", "other", "peripheral", "pc_parts_other"):
        h = " ".join(norm(title or "").split()[:9])
        if re.match(r"^(?:samsung\s*9\d0|9[89]0\s*pro|wd[ _]?black|sn\d{3}x?|crucial|kingston|seagate|firecuda|sabrent)\b", h) and re.search(r"\b(?:ps ?[2-5]|playstation ?[2-5]|xbox)\b", h) \
                and not re.search(r"\+|\bar\b|konsol|console", h):
            return "accessory", "a storage brand named for a console"
    # gaming gear named anywhere in the headline: "Logitech G29 stūre PS5/PC", "PS5 controller DualSense"
    if not category or category in ("console", "other", "peripheral"):
        for text in candidates:
            m = re.search(rf"\b{fold(FOR_WORDS)}\b\s+(?:\w+\s+){{0,2}}?(?:ps ?[2-5]|ps vita|playstation|xbox|nintendo|switch|steam deck)", text) if text else None
            if m and not re.search(fold(CONSOLE_NOUN), text[:m.start()]):
                return "accessory", "sold 'for' a console, not a console"
        for text in candidates:
            m = re.search(rf"(?<![a-z0-9]){fold(GAMING_ACCESSORY)}(?![a-z0-9])", text) if text else None
            if m:
                before = text[max(0, m.start() - 22):m.start()]
                has_console = re.search(fold(CONSOLE_NOUN), text[:140])
                if not has_console and not any(re.search(rf"(?<![a-z]){w}(?![a-z])", before) for w in ("ar", "with", "с", "un", "and", "komplekta", "ieskaitot")) and "+" not in before:
                    return "accessory", f"gaming gear for a console: '{m.group(0)}'"
    return "device", ""
