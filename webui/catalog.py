"""Art and rules facts the browser needs to draw choices, not just button labels.

The engine stays authoritative: this module only reads the same JSON files the
engine uses and points at the artwork it already ships.
"""
import json
import os

from helpers.FactionReference import faction_references

ART_ROOT = os.path.join("images", "resources")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(*parts):
    with open(os.path.join(ROOT, *parts)) as handle:
        return json.load(handle)


TECHS = _load("data", "techs.json")
PARTS = _load("data", "parts.json")
FACTIONS = _load("data", "factions.json")
DISCOVERIES = _load("data", "discoverytiles.json")


def art_url(relative):
    """A browser URL for a file under images/resources, or None when it is absent."""
    if not relative or not os.path.isfile(os.path.join(ROOT, ART_ROOT, relative)):
        return None
    return "/art/" + relative.replace(os.sep, "/")


def tech_image(tech_id):
    details = TECHS.get(tech_id)
    if not details:
        return None
    name = details["name"].lower().replace(" ", "_")
    track = details["track"]
    for folder in (track, "rare"):
        url = art_url(f"components/technology/{folder}/tech_{name}.png")
        if url:
            return url
    return None


def part_image(part_id):
    details = PARTS.get(part_id)
    if not details:
        return None
    name = details["name"].lower().replace(" ", "_")
    return art_url(f"components/upgrades/{name}.png")


def tech(tech_id):
    details = TECHS.get(tech_id)
    if not details:
        return {"id": tech_id, "name": tech_id, "track": "any", "cost": 0}
    return {"id": tech_id, "name": details["name"], "track": details["track"],
            "cost": details["base_cost"], "min_cost": details["min_cost"],
            "description": details.get("description", ""), "image": tech_image(tech_id)}


def part(part_id):
    details = PARTS.get(part_id)
    if not details:
        return {"id": part_id, "name": part_id, "image": None}
    return {"id": part_id, "name": details["name"], "image": part_image(part_id),
            "description": details.get("description", ""),
            "dice": details.get("dice", []), "nrg_use": details.get("nrg_use", 0),
            "nrg_src": details.get("nrg_src", 0), "comp": details.get("comp", 0),
            "shield": details.get("shield", 0), "hull": details.get("hull", 0),
            "range": details.get("range", 0), "speed": details.get("speed", 0)}


def discovery(disc_id):
    details = DISCOVERIES.get(disc_id)
    if not details:
        return {"id": disc_id, "name": disc_id, "image": None, "description": ""}
    name = details["name"].lower().replace(" ", "_")
    return {"id": disc_id, "name": details["name"],
            "image": art_url(f"components/discovery_tiles/discovery_{name}.png"),
            "description": details.get("description", "")}


def faction_board_image(artwork):
    if not artwork:
        return None
    for relative in (f"components/factions/{artwork}_board.png",
                     f"components/layouts/factionImages/{artwork}_image.png"):
        url = art_url(relative)
        if url:
            return url
    return None


def faction(key):
    row = FACTIONS.get(key)
    if row is None:
        return None
    return {
        "key": key,
        "name": row["name"],
        "artwork": row.get("artwork", key),
        "image": faction_board_image(row.get("artwork", key)),
        "reference": next((text for text, board in faction_references()
                           if board == ("terran_conglomerate_board.png" if key.startswith("ter")
                                        else f"{row.get('artwork', key)}_board.png")), ""),
        "abilities": row.get("abilities", []),
        "start": {field: row.get(field) for field in (
            "money", "science", "materials", "colony_ships", "trade_value",
            "explore_apt", "research_apt", "build_apt", "upgrade_apt", "move_apt",
            "influence_apt", "home_planet")},
        "ship": {field: row[field] for field in row if field.startswith("base_") or field.startswith("cost_")},
    }


def by_name(full_name):
    for key, row in FACTIONS.items():
        if row["name"] == full_name or full_name in row.get("name_aliases", []):
            return faction(key)
    return None


def snapshot():
    return {
        "techs": {tech_id: tech(tech_id) for tech_id in TECHS},
        "parts": {part_id: part(part_id) for part_id in PARTS},
        "discoveries": {disc_id: discovery(disc_id) for disc_id in DISCOVERIES},
    }
