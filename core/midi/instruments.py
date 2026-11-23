"""Catalogue of the sounds a MIDI track can be played with.

An instrument id is "<engine>:<preset>":
  sf:<program>     sampled General MIDI instrument (SoundFont)
  sfkit:<preset>   sampled drum kit (SoundFont, percussion bank)
  analog:<name>    virtual analog synth          fm:<name>      FM synth
  wt:<name>        wavetable synth               pluck:<name>   plucked string model
  organ:<name>     tonewheel organ               dm:<name>      analog drum machine
Labels are shown as is in the mixer (French UI).
"""
from . import synths

GROUPS = [
    ("sf", "Instruments réels (échantillons)"),
    ("pluck", "Cordes pincées (modèle physique)"),
    ("organ", "Orgue à roues phoniques"),
    ("analog", "Synthé analogique"),
    ("fm", "Synthé FM"),
    ("wt", "Synthé wavetable"),
    ("sfkit", "Batteries (échantillons)"),
    ("dm", "Boîte à rythmes analogique"),
]

SF = {
    0: "Piano à queue", 1: "Piano brillant", 4: "Piano électrique (Rhodes)", 5: "Piano électrique (FM)",
    6: "Clavecin", 7: "Clavinet", 11: "Vibraphone", 12: "Marimba", 16: "Orgue Hammond", 18: "Orgue rock",
    19: "Orgue d'église", 21: "Accordéon", 22: "Harmonica", 24: "Guitare nylon", 25: "Guitare folk (acier)",
    26: "Guitare jazz", 27: "Guitare électrique claire", 28: "Guitare étouffée", 29: "Guitare overdrive",
    30: "Guitare distorsion", 32: "Contrebasse", 33: "Basse électrique (doigts)", 34: "Basse électrique (médiator)",
    35: "Basse fretless", 36: "Basse slap", 38: "Basse synthé", 40: "Violon", 42: "Violoncelle",
    46: "Harpe", 48: "Ensemble de cordes", 49: "Cordes lentes", 50: "Cordes synthé", 52: "Chœur « aah »",
    53: "Voix « ooh »", 56: "Trompette", 57: "Trombone", 60: "Cor", 61: "Section de cuivres",
    64: "Saxophone soprano", 65: "Saxophone alto", 66: "Saxophone ténor", 68: "Hautbois", 71: "Clarinette",
    73: "Flûte", 75: "Flûte de pan", 80: "Lead carré", 81: "Lead dent de scie", 89: "Nappe chaude",
}
SFKIT = {0: "Kit standard", 8: "Kit « room »", 16: "Kit rock (power)", 24: "Kit électronique",
         25: "Kit 808/909 (échantillons)", 32: "Kit jazz", 40: "Kit balais"}
ANALOG = {"bass": "Basse analogique (Moog)", "acid": "Basse acid (303)", "lead": "Lead analogique",
          "pad": "Nappe analogique", "strings": "Cordes analogiques (string machine)",
          "brass": "Cuivres analogiques", "pluck": "Pluck analogique"}
FM = {"epiano": "Piano électrique FM (DX)", "bass": "Basse FM", "bell": "Cloches FM", "brass": "Cuivres FM",
      "organ": "Orgue FM", "clav": "Clavinet FM", "marimba": "Marimba FM"}
WT = {"sweep": "Wavetable balayage", "pad": "Nappe numérique", "lead": "Lead numérique",
      "voice": "Voix synthétique (formants)", "bass": "Basse wavetable"}
PLUCK = {"nylon": "Guitare nylon (corde modélisée)", "steel": "Guitare acier (corde modélisée)",
         "electric": "Guitare électrique claire (corde modélisée)",
         "overdrive": "Guitare saturée (corde modélisée + ampli)", "bass": "Basse pincée (corde modélisée)",
         "harp": "Harpe (corde modélisée)"}
ORGAN = {"jazz": "Orgue jazz (888000000)", "rock": "Orgue rock", "gospel": "Orgue gospel",
         "church": "Grand orgue"}
DM = {"808": "TR-808 (synthèse)", "909": "TR-909 (synthèse)"}
LABELS = {"sf": SF, "sfkit": SFKIT, "analog": ANALOG, "fm": FM, "wt": WT, "pluck": PLUCK,
          "organ": ORGAN, "dm": DM}

# First entry = default. The rest are the sounds made for that kind of part.
RECOMMENDED = {
    "vocals": ["sf:53", "sf:73", "sf:65", "wt:voice", "analog:lead", "wt:lead", "sf:11"],
    "backing_vocals": ["sf:52", "sf:53", "wt:voice", "analog:pad", "wt:pad"],
    "bass": ["sf:33", "sf:34", "sf:35", "sf:32", "pluck:bass", "analog:bass", "analog:acid", "fm:bass", "wt:bass"],
    "guitar": ["sf:27", "sf:25", "sf:24", "sf:26", "sf:29", "sf:30", "pluck:electric", "pluck:steel",
               "pluck:nylon", "pluck:overdrive", "analog:pluck", "fm:clav"],
    "electric_guitar": ["sf:27", "sf:26", "sf:29", "sf:30", "sf:28", "pluck:electric", "pluck:overdrive",
                        "analog:pluck", "fm:clav"],
    "acoustic_guitar": ["sf:25", "sf:24", "pluck:steel", "pluck:nylon", "pluck:harp", "sf:46"],
    "piano": ["sf:0", "sf:1", "sf:4", "fm:epiano", "sf:5", "sf:7", "fm:clav", "sf:11", "fm:marimba"],
    "organ": ["organ:jazz", "organ:rock", "organ:gospel", "organ:church", "sf:16", "sf:18", "sf:19", "fm:organ"],
    "synth": ["analog:lead", "analog:pad", "analog:brass", "wt:sweep", "wt:pad", "wt:lead", "fm:bell", "sf:81"],
    "brass": ["sf:61", "sf:56", "sf:57", "sf:66", "sf:65", "analog:brass", "fm:brass"],
    "winds": ["sf:73", "sf:71", "sf:68", "sf:65", "sf:75", "wt:lead"],
    "strings": ["sf:48", "sf:49", "sf:40", "sf:42", "analog:strings", "analog:pad", "wt:pad"],
    "other": ["sf:48", "sf:0", "sf:4", "analog:pad", "analog:strings", "wt:pad", "fm:epiano"],
}
DRUM_RECOMMENDED = ["sfkit:0", "sfkit:8", "sfkit:16", "sfkit:32", "sfkit:40", "sfkit:24", "sfkit:25",
                    "dm:808", "dm:909"]
# General MIDI program written in the .mid file of each stem.
GM_PROGRAM = {"vocals": 53, "backing_vocals": 52, "bass": 33, "guitar": 27, "electric_guitar": 27,
              "acoustic_guitar": 25, "piano": 0, "organ": 16, "synth": 81, "brass": 61, "winds": 73,
              "strings": 48, "other": 48}


def label(instrument):
    engine, _, preset = instrument.partition(":")
    table = LABELS.get(engine, {})
    key = int(preset) if engine in ("sf", "sfkit") and preset.isdigit() else preset
    return table.get(key, instrument)


def slug(instrument):
    """Stem name made from the label of an instrument ("Cordes (ensemble)" -> "cordes_ensemble")."""
    import re
    import unicodedata
    text = label(instrument).split("(")[0].strip() or label(instrument)     # the detail in brackets is dropped
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "midi"


def track_title(stem, instrument, drums):
    """Name shown for a MIDI track once the user chose its sound.

    A pitched track is what its instrument says; a kit piece stays a piece of a kit.
    """
    name = label(instrument)
    return f"{stem} · {name}" if drums and stem != "drums" else name


def track_slug(stem, instrument, drums):
    """Stem name of a MIDI track written out as audio under its own name (pre-mix)."""
    return f"{stem}_{slug(instrument)}" if drums and stem != "drums" else slug(instrument)


def exists(instrument, drums):
    engine, _, preset = instrument.partition(":")
    if drums != (engine in ("sfkit", "dm")):
        return False
    key = int(preset) if engine in ("sf", "sfkit") and preset.isdigit() else preset
    return key in LABELS.get(engine, {})


def default_for(stem, drums, soundfont=True):
    """Default sound of a stem; falls back on a built-in synth when no SoundFont player is there."""
    choices = DRUM_RECOMMENDED if drums else RECOMMENDED.get(stem, RECOMMENDED["other"])
    for c in choices:
        if soundfont or not c.startswith("sf"):
            return c
    return "dm:808" if drums else "analog:lead"


def options_for(stem, drums, soundfont=True):
    """Menu for one track: {'recommended': [...], 'groups': [{'label', 'items': [{'id','label'}]}]}."""
    def ok(i):
        return (soundfont or not i.startswith("sf")) and (synths.HAVE_NUMBA or i.split(":")[0] in ("sf", "sfkit", "dm"))
    rec = [i for i in (DRUM_RECOMMENDED if drums else RECOMMENDED.get(stem, RECOMMENDED["other"])) if ok(i)]
    groups = []
    for engine, title in GROUPS:
        if drums != (engine in ("sfkit", "dm")):
            continue
        items = [{"id": f"{engine}:{k}", "label": v} for k, v in LABELS[engine].items() if ok(f"{engine}:{k}")]
        if items:
            groups.append({"label": title, "items": items})
    return {"recommended": [{"id": i, "label": label(i)} for i in rec], "groups": groups}
