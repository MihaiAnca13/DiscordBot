"""Create a real Eclipse game and its Discord channels.

Shared by the `/create_new_game` slash command and the OBG server-to-server API
so an OBG-created game is the same game the bot would have created by hand.
"""
import asyncio
import discord
from Buttons.Draft import DraftButtons
from helpers.DrawHelper import DrawHelper
from helpers.GamestateHelper import GamestateHelper
from helpers.FactionReference import faction_references
from setup.GameInit import GameInit
from webui import runtime


async def _get_or_create_category(guild, category_name):
    for category in guild.categories:
        if category.name == category_name:
            return category
    overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False)}
    return await guild.create_category(category_name, overwrites=overwrites)


async def _get_or_create_role(guild, role_name):
    for role in guild.roles:
        if role.name == role_name:
            return role
    return await guild.create_role(name=role_name, mentionable=True)


async def launch_game(
    guild,
    game_name,
    player_list,
    player_count,
    *,
    display_names=None,
    members=None,
    ai_ships="def",
    rift_cannon=True,
    turn_order_variant=True,
    galactic_event_tiles=False,
    hyperlanes=False,
    community_parts=False,
    community_rep_mod=False,
    ban_factions=False,
    alliances=False,
    community_factions=False,
):
    """Create the game, channels, setup messages and draft.

    ``player_list`` is ``[[discord_id, mention], ...]`` in Discord id order.
    ``display_names`` maps ids to the name stored as the browser-visible
    username. ``members`` maps ids to fetched guild members when the bot's
    member cache cannot be trusted.
    """
    new_game = GameInit(game_name, player_list, ai_ships, rift_cannon, turn_order_variant,
                        community_parts, community_rep_mod, community_factions=community_factions)
    new_game.create_game()
    game_id = new_game.gamestate["game_id"]
    game = GamestateHelper(None, game_id)
    for player_id, _mention in player_list:
        name = (display_names or {}).get(str(player_id))
        if name:
            game.gamestate["players"][str(player_id)]["username"] = name
    game.update()

    number = int(game_id[3:])
    if number <= 10:
        category_name = "Games #1-10"
    else:
        start = 10 * ((number - 1) // 10) + 1
        category_name = f"Games #{start}-{start + 9}"
    category = await _get_or_create_category(guild, category_name)

    role = await _get_or_create_role(guild, game_id)
    overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False),
                  role: discord.PermissionOverwrite(read_messages=True, manage_messages=True)}

    for player_id, _mention in player_list:
        member = (members or {}).get(str(player_id)) or guild.get_member(player_id)
        if member:
            await member.add_roles(role)
            overwrites[member] = discord.PermissionOverwrite(read_messages=True, manage_messages=True)
    observers = discord.utils.get(guild.roles, name="Observers")
    if observers:
        overwrites[observers] = discord.PermissionOverwrite(read_messages=True)

    tabletalk = await guild.create_text_channel(f"{game_id}-{game_name}",
                                               category=category, overwrites=overwrites)
    actions = await guild.create_text_channel(f"{game_id}-actions",
                                              category=category, overwrites=overwrites)
    thread = await actions.create_thread(name=f"{game_id}-bot-map-updates", auto_archive_duration=10080,
                                         type=discord.ChannelType.public_thread)
    new_game.update_num()

    player_count = min(max(player_count, 2), 9)
    notes = ""
    if hyperlanes:
        if player_count not in (4, 5):
            hyperlanes = False
            notes += ("## Hyperlanes cannot be enabled in anything except 4 or 5 player games"
                      " at the moment, so they have not been enabled for this game")
        else:
            notes += "## Hyperlanes have been enabled for this game"
    if galactic_event_tiles:
        notes += "\n## Galactic Event Tiles and Nebula Sectors have been added to this game"
    if rift_cannon:
        notes += "\n## Rift Cannons have been added to this game"
    if alliances:
        if player_count < 4:
            alliances = False
            notes += ("\n## Alliances require at least 4 players,"
                      " so they have not been enabled for this game")
        else:
            notes += "\n## Alliances have been enabled for this game"
    if notes:
        await actions.send(notes)

    game.setAlliances(alliances)
    game.setup_techs_and_outer_rim(player_count, galactic_event_tiles, hyperlanes)
    drawing = DrawHelper(game.gamestate)

    minor_species = "\n".join(game.gamestate["minor_species"])
    await thread.send(role.mention + " pinging you here")
    await actions.send("Initial tech draw is as follows", file=drawing.show_available_techs())
    await actions.send(f"{role.mention}, draft factions and turn position in the manner of your choice,"
                       " then setup the game with /setup game. "
                       "Enter the players in the order they should take turns in"
                       " (i.e. enter first player first). "
                       "A draft has been started for you that you may use instead of the slash command.")
    await actions.send("A common way to draft factions is to generate a random pick order"
                       " and then have the turn order be the reverse of that pick order. "
                       "For your convenience, the following random pick order was generated,"
                       " but you may ignore it. \n"
                       "This game has been set to auto include minor species,"
                       " 4 of which have been drawn at random below. "
                       "If you want to disable this, you may use `/game disable_minor_species`. "
                       "The minor species are as follows:\n" + minor_species,
                       file=drawing.show_minor_species())
    await actions.send("AI stats look like this", file=await asyncio.to_thread(drawing.show_AI_stats))
    await DraftButtons.startDraft(game, player_list, _DraftGuild(guild),
                                  runtime.record_channel(actions, game_id), ban_factions)

    faction_thread = await actions.create_thread(name="Faction Reference", auto_archive_duration=10080)
    board_prefix = "images/resources/components/factions/"
    community_sheets = {}
    standard_boards = {board for _, board in faction_references(False)}
    for message, board_file in faction_references(community_factions):
        if board_file in standard_boards:
            await faction_thread.send(message, file=drawing.get_file(board_prefix + board_file))
        else:
            community_sheets[board_file] = (message, board_file)
    await faction_thread.send("\n".join(["Rift Reference"]),
                              file=drawing.get_file(board_prefix + "Rift_Reference.png"))
    await faction_thread.send("\n".join(["Minor Species Reference"]),
                              file=drawing.get_file(board_prefix + "Minor_Species_Reference.png"))
    await faction_thread.send("\n".join(["Discovery Reference"]),
                              file=drawing.get_file(board_prefix + "Discovery_Reference.png"))
    await faction_thread.send(role.mention + " pinging you here, which contains all the faction sheets")

    return {
        "id": game_id,
        "tabletalk_url": tabletalk.jump_url,
        "actions_url": actions.jump_url,
        "faction_thread": faction_thread,
        "drawing": drawing,
        "community_sheets": community_sheets,
    }


class _DraftGuild:
    """The draft only reads ``guild``; keep launch callable off an interaction."""

    def __init__(self, guild):
        self.guild = guild
