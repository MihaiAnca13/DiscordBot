import discord
from discord.ui import View, Button

from helpers import FactionData
from helpers.GamestateHelper import GamestateHelper
from helpers.Turtugan import Harvester


class HarvesterButtons:
    RESOURCE_LABELS = {"money": "Money", "science": "Science", "material": "Material"}

    @staticmethod
    async def startPlace(game: GamestateHelper, player, interaction: discord.Interaction):
        if not FactionData.has(player, "harvester"):
            return
        round_num = game.gamestate.get("roundNum", 0)
        if player.get("harvester_upkeep_started_round") != round_num:
            await interaction.followup.send("Harvester allocations are only available at the beginning of Upkeep.",
                                            ephemeral=True)
            return
        view = View()
        for position in Harvester.sectors_with_harvester(game, player):
            placements = [item for item in player.get("harvester_placements", [])
                          if item["position"] == position]
            if len(placements) >= Harvester.starbases(game, player, position):
                continue
            available = [(square, index) for square, index
                         in Harvester.unsettled_squares(game.gamestate["board"][position])
                         if not Harvester.occupied(game, position, square, index)]
            if not available:
                continue
            count = Harvester.starbases(game, player, position)
            view.add_item(Button(label=f"{position} ({count} Harvester{'' if count == 1 else 's'})",
                                 style=discord.ButtonStyle.blurple,
                                 custom_id=f"FCID{player['color']}_harvesterSector_{position}"))
        if not view.children:
            player["harvester_upkeep_allocated_round"] = game.gamestate.get("roundNum", 0)
            game.update()
            await interaction.channel.send(f"{player['player_name']} has finished Harvester allocations. "
                                           "Press Run Upkeep again to continue.")
            return
        await interaction.channel.send(f"{player['player_name']}, allocate a Harvester to a planet in its sector."
                                       " You can choose a different planet during the next Upkeep.", view=view)

    @staticmethod
    async def showSquares(game: GamestateHelper, player, interaction: discord.Interaction, customID: str):
        if player.get("harvester_upkeep_started_round") != game.gamestate.get("roundNum", 0):
            await interaction.followup.send("This Harvester allocation is no longer current.", ephemeral=True)
            return
        position = customID.split("_")[1]
        if f"{player['color']}-sb" not in game.gamestate["board"].get(position, {}).get("player_ships", []):
            await interaction.followup.send("That sector no longer has one of your Harvesters.", ephemeral=True)
            return
        view = View()
        for square, index in Harvester.unsettled_squares(game.gamestate["board"][position]):
            if Harvester.occupied(game, position, square, index):
                continue
            resource = Harvester.resource_for(square)
            label = f"{square.replace('adv', ' Advanced ').replace('_', ' ').capitalize()} ({index})"
            custom_id = f"FCID{player['color']}_placeHarvester_{position}_{square}_{index}"
            if resource is not None:
                custom_id += f"_{resource}"
            view.add_item(Button(label=label, style=discord.ButtonStyle.green, custom_id=custom_id))
        if not view.children:
            await interaction.followup.send("That sector has no unsettled planet left for a Harvester.",
                                            ephemeral=True)
            return
        await interaction.message.delete()
        await interaction.channel.send(f"{player['player_name']}, choose the planet in {position}"
                                       " your Harvester produces from.", view=view)

    @staticmethod
    async def place(game: GamestateHelper, player, interaction: discord.Interaction, customID: str):
        parts = customID.split("_")
        position, square, index = parts[1], parts[2], parts[3]
        resource = parts[4] if len(parts) > 4 else Harvester.resource_for(square)
        if resource is None:
            view = View()
            for choice in Harvester.RESOURCES:
                view.add_item(Button(label=HarvesterButtons.RESOURCE_LABELS[choice],
                                     style=discord.ButtonStyle.blurple,
                                     custom_id=(f"FCID{player['color']}_harvesterResource_"
                                                f"{position}_{square}_{index}_{choice}")))
            await interaction.message.delete()
            await interaction.channel.send(f"{player['player_name']}, a grey planet may produce any resource."
                                           " Choose one for this Harvester.", view=view)
            return
        await HarvesterButtons.finishPlace(game, player, interaction, position, square, index, resource)

    @staticmethod
    async def placeResource(game: GamestateHelper, player, interaction: discord.Interaction, customID: str):
        parts = customID.split("_")
        position, square, index, resource = parts[1], parts[2], parts[3], parts[4]
        await HarvesterButtons.finishPlace(game, player, interaction, position, square, index, resource)

    @staticmethod
    async def finishPlace(game: GamestateHelper, player, interaction: discord.Interaction,
                          position: str, square: str, index: str, resource: str):
        if player.get("harvester_upkeep_started_round") != game.gamestate.get("roundNum", 0):
            await interaction.followup.send("This Harvester allocation is no longer current.", ephemeral=True)
            return
        if not Harvester.record(game, player, position, square, index, resource):
            await interaction.followup.send("That planet is no longer available for this Harvester.",
                                            ephemeral=True)
            return
        await interaction.message.delete()
        await interaction.channel.send(f"{player['player_name']} placed a Harvester over the {square} planet"
                                       f" in {position}, producing 1 {resource} this Upkeep.")
        await HarvesterButtons.startPlace(game, player, interaction)
