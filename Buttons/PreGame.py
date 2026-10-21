import asyncio
import discord
from Buttons.DiscoveryTile import DiscoveryTileButtons
from Buttons.Population import PopulationButtons
from Buttons.Research import ResearchButtons
from Buttons.Turn import TurnButtons
from helpers.GamestateHelper import GamestateHelper
from discord.ui import View, Button


class PreGameButtons:
    """The phase between setting the game up and the first turn.

    Factions that have something to do before the game starts do it here: the Exiles
    populate the Orbital in their starting sector, the Atlantians resolve a discovery
    tile, Remnants of Ra put a cube on the disc of their artifact sector and the
    Techno-Mages may buy a technology. The first turn only starts once they are all done.
    """

    # the pre-game action of each faction that has one
    TASKS = {"The Exiles": "orbital_pop",
             "Atlantians": "discovery_tile",
             "Remnants of Ra": "artifact_cube",
             "Techno-Mages": "setup_tech"}

    @staticmethod
    def taskFromButton(customID: str):
        """The pre-game action a button press completes, if it completes one."""
        if customID.startswith("preGameOrbital"):
            return "orbital_pop"
        if customID.startswith("ancientsCube"):
            return "artifact_cube"
        if customID.startswith("keepDiscForPoints") or customID.startswith("usedDiscForAbility"):
            return "discovery_tile"
        if customID.startswith("declineSetupTech"):
            return "setup_tech"
        # a tech on the "any" track is only researched once its track is picked
        if customID.startswith("getTech") and not customID.endswith("_any"):
            return "setup_tech"
        return None

    @staticmethod
    async def startPreGame(game: GamestateHelper, interaction: discord.Interaction, player_ids):
        """Ask every faction that has something to do before the game starts to do it now."""
        game.gamestate["pre_game"] = {"first_player": str(player_ids[0]), "tasks": []}
        game.update()
        for player_id in player_ids:
            player = game.get_player(player_id, interaction)
            if player is None:
                continue
            task = PreGameButtons.TASKS.get(player.get("name"))
            if task is None:
                continue
            # the task is recorded before the offer goes out, so a quick press is not lost
            game.gamestate["pre_game"]["tasks"].append([str(player_id), task])
            game.update()
            home = game.getLocationFromID(player["home_planet"])
            if task == "orbital_pop":
                offered = await PreGameButtons.offerExilesOrbital(game, player, interaction, home)
            elif task == "discovery_tile":
                game.addDiscTile(home)
                offered = await DiscoveryTileButtons.exploreDiscoveryTile(game, home, interaction, player)
            elif task == "artifact_cube":
                offered = await PopulationButtons.offerAncientsCube(game, player, interaction, home)
            else:
                offered = await ResearchButtons.offerSetupTech(game, player, interaction)
            if not offered:
                # this faction cannot do this action after all, so the game does not wait for it
                game.gamestate["pre_game"]["tasks"].remove([str(player_id), task])
                game.update()
        if not game.preGameTasks():
            await PreGameButtons.startGame(game, interaction, player_ids[0])
        else:
            await interaction.channel.send("The game starts once every faction has finished"
                                           " their pre-game action.")

    @staticmethod
    async def completeTask(game: GamestateHelper, interaction: discord.Interaction, player, customID: str):
        """Record that a player finished a pre-game action, and start the game if it was the last one."""
        task = PreGameButtons.taskFromButton(customID)
        if task is None:
            return
        player_id = game.get_player_from_color(player["color"])
        tasks = game.preGameTasks()
        if [player_id, task] not in tasks:
            return
        tasks.remove([player_id, task])
        game.update()
        if not tasks:
            await PreGameButtons.startGame(game, interaction, game.gamestate["pre_game"]["first_player"])

    @staticmethod
    async def startGame(game: GamestateHelper, interaction: discord.Interaction, first_player):
        """Start the first turn of the game."""
        player = game.get_player(first_player, interaction)
        asyncio.create_task(game.showUpdate("Start of Game", interaction))
        TurnButtons.startNewTurn(player, game)
        view = TurnButtons.getStartTurnButtons(game, player, "dummy")
        game.updatePingTime()
        await interaction.channel.send(f"## {game.getPlayerEmoji(player)} started their turn.")
        await interaction.channel.send(f"{player['player_name']} use these buttons to do your turn"
                                       + game.displayPlayerStats(player), view=view)

    @staticmethod
    async def offerExilesOrbital(game: GamestateHelper, player, interaction: discord.Interaction, tile: str):
        """The Exiles put a population cube on the Orbital in their starting sector before the game starts."""
        options = [pop for pop in ["money", "science"]
                   if player["colony_ships"] > 0 and player[f"{pop}_pop_cubes"] > 0]
        if not options:
            return False
        view = View()
        for pop in options:
            view.add_item(Button(label=pop.capitalize(), style=discord.ButtonStyle.blurple,
                                 custom_id=f"FCID{player['color']}_preGameOrbital_{pop}"))
        await interaction.channel.send(f"{player['player_name']}, before the game starts you place a population"
                                       f" cube on the Orbital in your starting sector (tile {tile})."
                                       " Choose which type of cube to place.", view=view)
        return True

    @staticmethod
    async def placeExilesOrbital(game: GamestateHelper, player, interaction: discord.Interaction, customID: str):
        pop = customID.split("_")[1]
        tile = game.getLocationFromID(player["home_planet"])
        if game.gamestate["board"][tile].get("orbital_pop", [0])[0]:
            await interaction.followup.send("Your Orbital already has a population cube on it.", ephemeral=True)
            return
        if not game.add_pop_specific("orbital", pop, 0, tile, game.get_player_from_color(player["color"])):
            await interaction.followup.send("You need an unused colony ship and a cube"
                                            " to populate your Orbital.", ephemeral=True)
            return
        await interaction.message.edit(view=None)
        await interaction.channel.send(f"{player['player_name']} placed a {pop} population cube on the Orbital"
                                       f" in tile {tile}.")

    @staticmethod
    async def declineSetupTech(game: GamestateHelper, player, interaction: discord.Interaction):
        """The Techno-Mages may pass on the technology they may buy before the game starts."""
        await interaction.message.delete()
        await interaction.channel.send(f"{player['player_name']} is not buying a technology before the game starts.")
