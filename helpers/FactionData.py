"""Faction facts from data/factions.json.

A faction's numbers, colour, artwork key and abilities live in the file, not in
`if player["name"] == ...` branches. A game saved before a field was added keeps
its old copy of the row, so facts are read from the file here, keyed by name.
"""
import json

with open("data/factions.json", "r") as f:
    FACTIONS = json.load(f)

BY_NAME = {faction["name"]: faction for faction in FACTIONS.values()}


def of(player):
    """The faction row for a player: the player's own copy wins, the file fills in what a save predates."""
    if not player:
        return {}
    row = BY_NAME.get(player.get("name"))
    if row is None:
        return player
    return {**row, **player}


def has(player, ability):
    """Whether the player's faction declares the ability."""
    return ability in of(player).get("abilities", [])


def artwork_name(full_name):
    """The image and emoji key of a faction: artwork names differ from data keys (exl -> exile)."""
    return BY_NAME.get(full_name, {}).get("artwork", full_name)
