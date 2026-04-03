from __future__ import annotations

import discord

EMBED_COLOR = 0xff5100
SUCCESS_EMBED_COLOR = 0x57F287
UNLINK_EMBED_COLOR = 0x5865F2
_DEFAULT_EMBED_FOOTER = "Contact randomnoobster for help or bug reports"


def verification_success_embed(*, relinked: bool) -> discord.Embed:
    if relinked:
        title = "Verification updated"
        description = (
            "Your Discord account is now linked to your **new** nation. "
            'Commands that use "you" will target this nation from now on.'
        )
    else:
        title = "Nation linked"
        description = (
            "Your Discord account is linked to your Politics & War nation. "
            "Autolycus can recognize you in slash commands that need a nation."
        )
    embed = discord.Embed(title=title, description=description, color=SUCCESS_EMBED_COLOR)
    embed.set_footer(text=_DEFAULT_EMBED_FOOTER)
    return embed


def verification_unlinked_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Account unlinked",
        description=(
            "Your Discord account is no longer tied to a Politics & War nation. "
            "Run `/verify` whenever you want to link again."
        ),
        color=UNLINK_EMBED_COLOR,
    )
    embed.set_footer(text=_DEFAULT_EMBED_FOOTER)
    return embed


def embed_pager(title: str, fields: list[dict[str, str]], description: str = "", color: int = EMBED_COLOR, inline: bool = True) -> list[discord.Embed]:
    num_pages = max(1, (len(fields) + 23) // 24)
    embeds = [discord.Embed(title=f"{title} page {i+1}", description=description, color=color) for i in range(num_pages)]
    for idx, field in enumerate(fields):
        page_idx = idx // 24
        embeds[page_idx].add_field(name=field['name'], value=field['value'], inline=inline)
    return embeds


def nation_overview_embed(nation: dict, discord_info: str, alliance_info: str, military_info: str, military_info_2: str) -> discord.Embed:
    embed = discord.Embed(title=nation['nation_name'], url=f"https://politicsandwar.com/nation/id={nation['id']}", color=EMBED_COLOR)
    embed.add_field(name="Discord Info", value=discord_info, inline=False)

    nation_info = (
        f"> Nation Name: [{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']})\n"
        f"> Leader Name: {nation['leader_name']}\n"
        f"> Cities: [{nation['num_cities']}](https://politicsandwar.com/city/manager/n={nation['nation_name'].replace(' ', '%20')})\n"
        f"> War Policy: [{nation['warpolicy']}](https://politicsandwar.com/pwpedia/war-policy/)\n"
        f"> Dom. Policy: [{nation['dompolicy']}](https://politicsandwar.com/pwpedia/domestic-policy/)"
    )
    embed.add_field(name="Nation Info", value=nation_info)

    nation_info_2 = (
        f"> Score: `{nation['score']}`\n"
        f"> Def. Range: `{round(nation['score']/2.5)}`-`{round(nation['score']/0.75)}`\n"
        f"> Off. Range: `{round(nation['score']*0.75)}`-`{round(nation['score']*2.5)}`\n"
        f"> Color: [{nation['color'].capitalize()}](https://politicsandwar.com/leaderboards/display=color)\n"
        f"> Turns of VM: `{nation['vmode']}`"
    )
    embed.add_field(name="\u200b", value=nation_info_2)

    embed.add_field(name="Alliance Info", value=alliance_info, inline=False)
    embed.add_field(name="Military Info", value=military_info)
    embed.add_field(name="\u200b", value=military_info_2, inline=True)
    embed.set_footer(text="Contact randomnoobster for help or bug reports")
    return embed
