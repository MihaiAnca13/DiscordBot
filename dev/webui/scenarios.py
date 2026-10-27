"""Fabricate valid sandbox saves for flows that take a full round to reach.

    docker compose -f compose.webui.yaml stop webui
    docker compose -f compose.webui.yaml run --rm webui python -m dev.webui.scenarios combat
    docker compose -f compose.webui.yaml up -d --wait webui

Only the named development volumes are touched; ``seed.reset`` refuses any save
folder other than /sandbox/games.
"""
import asyncio
import sys

import discord
from helpers.CombatHelper import Combat
from webui.transport import WebInteraction

from dev.webui.seed import reset


def members(game):
    players = game.gamestate["players"]
    return {"names": {pid: stats.get("color") for pid, stats in players.items()},
            "colors": [stats.get("color") for stats in players.values()]}


def connect_homes(game):
    """Place the ring-1 sectors that sit between the centre and both homes."""
    game.add_tile("101", 0, "307")
    game.add_tile("102", 0, "309")


def all_passed_prompt(game, store):
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Put Down Population", style=discord.ButtonStyle.gray,
                                    custom_id="startPopDrop"))
    view.add_item(discord.ui.Button(label="Run Upkeep", style=discord.ButtonStyle.blurple,
                                    custom_id="runUpkeep"))
    return view


async def scenario_combat(game, store):
    game.add_tile("102", 0, "307")
    game.add_control("blue", "102")
    game.add_units(["blue-int"], "102")
    game.add_units(["red-int"], "102")
    game.noteUnitEntry("red", "102")
    interaction = WebInteraction(store, "aeb1", "1", members=members(game))
    await Combat.startCombatThreads(game, interaction)
    await asyncio.sleep(0.5)


async def scenario_movement(game, store):
    connect_homes(game)


async def scenario_upkeep(game, store):
    for player in game.gamestate["players"].values():
        player["passed"] = True
    game.initilizeKey("activePlayerColor")
    game.update()
    from webui.transport import Surface
    surface = Surface(store, "aeb1", seat="1")
    await surface.channel.send("all players have passed, you may use this button to start the next round.",
                               view=all_passed_prompt(game, store))


async def scenario_scoring(game, store):
    game.gamestate["roundNum"] = 8
    await scenario_upkeep(game, store)


async def scenario_recovery(game, store):
    for row in store.visible_history("aeb1", ""):
        store.remove(row["id"])


async def scenario_bankrupt(game, store):
    game.gamestate["players"]["1"]["influence_discs"] = 2
    game.gamestate["players"]["1"]["money"] = 0
    await scenario_upkeep(game, store)


SCENARIOS = {
    "combat": scenario_combat,
    "movement": scenario_movement,
    "upkeep": scenario_upkeep,
    "scoring": scenario_scoring,
    "recovery": scenario_recovery,
    "bankrupt": scenario_bankrupt,
}


async def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "movement"
    if name not in SCENARIOS:
        raise SystemExit(f"scenario must be one of: {', '.join(SCENARIOS)}")
    game, store = await reset()
    await SCENARIOS[name](game, store)
    store.close()
    print(f"Scenario {name}: aeb1 ready")


if __name__ == "__main__":
    asyncio.run(main())
