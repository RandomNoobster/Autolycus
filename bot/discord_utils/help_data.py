"""Centralized help metadata for all Autolycus Discord commands.

Each command entry contains:
- short: Concise description shown in /help list and Discord's autocomplete (max ~100 chars).
- long: Detailed explanation of what the command does and how it works.
- parameters: Dict mapping parameter names to human-friendly descriptions.
- examples: List of example usages.
- notes: Optional tips, caveats, or extra context.
"""

from typing import Dict, List, Optional, TypedDict


class CommandHelp(TypedDict, total=False):
    short: str
    long: str
    parameters: Dict[str, str]
    examples: List[str]
    notes: Optional[str]


COMMAND_HELP: Dict[str, CommandHelp] = {
    # ── General Commands ──────────────────────────────────────────────
    "who": {
        "short": "Look up detailed information about any nation",
        "long": (
            "Displays a comprehensive nation overview including Discord verification "
            "status, alliance info (name, position, seniority, score, color, member count), "
            "full military breakdown (soldiers, tanks, aircraft, ships with current / max / "
            "daily production values), MMR, missiles, nukes, offensive & defensive war slots, "
            "Iron Dome, Vital Defense System, and remaining beige turns."
        ),
        "parameters": {
            "person": (
                "Who to look up. Accepts a Discord @mention, Discord user ID, nation ID, "
                "nation name, leader name, or a full nation link. "
                "If omitted, looks up your own nation."
            ),
        },
        "examples": [
            "`/who` — look up yourself",
            "`/who 12345` — look up nation #12345",
            "`/who @SomeUser` — look up a Discord user's linked nation",
        ],
    },
    "builds": {
        "short": "Find the optimal city builds for a given infra & land level",
        "long": (
            "Calculates the best city building configurations that maximize daily net "
            "income for a specific infrastructure and land level. Takes your nation's "
            "projects and policies into account. Returns the top build with a JSON "
            "template you can paste in-game, plus a link to the full results page "
            "where you can browse all viable configurations."
        ),
        "parameters": {
            "infra": (
                "The infrastructure level to optimize for. **Must be a multiple of 50** "
                "(e.g. 1500, 2000, 2500)."
            ),
            "land": "The amount of land the city should have (e.g. 3000).",
            "mmr": (
                "Minimum Military Requirement in the format `barracks/factory/hangar/drydock` "
                "(e.g. `5/3/0/0`). Use `any` for no military constraint. Defaults to `0/0/0/0`."
            ),
            "person": (
                "The nation to calculate builds for. Accepts the same formats as `/who`. "
                "Defaults to you."
            ),
        },
        "examples": [
            "`/builds 2000 3000` — best builds for 2k infra, 3k land, no military",
            "`/builds 1500 2500 5/3/0/0` — with a 5/3/0/0 MMR constraint",
            "`/builds 2000 3000 any @SomeUser` — any MMR, for another player",
        ],
    },
    "revenue nation": {
        "short": "View a nation's full daily revenue breakdown",
        "long": (
            "Calculates a nation's daily revenue across every resource type. Shows "
            "separate fields for incomes, expenses, net revenue per resource, and total "
            "monetary net income. Accounts for the nation's color bloc, current market "
            "prices, alliance treasures, global radiation, and seasonal modifiers."
        ),
        "parameters": {
            "person": (
                "The nation to calculate revenue for. Accepts Discord @mention, user ID, "
                "nation ID, nation name, or nation link. Defaults to your own nation."
            ),
        },
        "examples": [
            "`/revenue nation` — your own revenue",
            "`/revenue nation 12345` — revenue for nation #12345",
            "`/revenue nation @SomeUser` — revenue for a Discord user's nation",
        ],
    },
    "revenue alliance": {
        "short": "View an alliance's total daily revenue across all members",
        "long": (
            "Aggregates the daily revenue of every non-applicant member in an "
            "alliance. Displays totals for all resource types plus total cash income "
            "and monetary net income. Optionally includes gray (untaxed) nations, "
            "which are excluded by default."
        ),
        "parameters": {
            "alliance": (
                "The alliance to calculate for. Accepts an alliance name, ID, or acronym. "
                "Autocomplete is supported — start typing and pick from the list."
            ),
            "include_grey": (
                "Whether to include gray-bloc nations in the calculation. "
                "Defaults to No."
            ),
        },
        "examples": [
            "`/revenue alliance Rose` — revenue for alliance 'Rose'",
            "`/revenue alliance 770 True` — include gray nations",
        ],
    },
    "botinfo": {
        "short": "View bot statistics and useful links",
        "long": (
            "Shows how many servers and users the bot serves, how many users have "
            "verified, and provides quick links to the GitHub repository, bot invite "
            "link, Privacy Policy, and Terms of Service."
        ),
        "parameters": {},
        "examples": ["`/botinfo`"],
    },
    "verify": {
        "short": "Link your Discord account to your Politics & War nation",
        "long": (
            "Verifies your identity by checking that your Discord username matches "
            "the one set on your Politics & War nation page. If they don't match, "
            "you'll receive step-by-step instructions to update your in-game Discord "
            "username and try again. Once verified, other commands can automatically "
            "detect your nation without you having to type your nation ID every time."
        ),
        "parameters": {
            "nation_id": (
                "Your nation ID or full nation link "
                "(e.g. `12345` or `https://politicsandwar.com/nation/id=12345`)."
            ),
        },
        "examples": [
            "`/verify 12345`",
            "`/verify https://politicsandwar.com/nation/id=12345`",
        ],
        "notes": (
            "You only need to verify once. To re-verify with a different nation, "
            "use `/unverify` first."
        ),
    },
    "unverify": {
        "short": "Unlink your Discord account from your P&W nation",
        "long": (
            "Removes the link between your Discord account and your Politics & War "
            "nation. After unverifying, commands will no longer auto-detect your nation "
            "and you will need to provide your nation ID manually."
        ),
        "parameters": {},
        "examples": ["`/unverify`"],
    },

    # ── Military / Target-Finding Commands ────────────────────────────
    "raids": {
        "short": "Find profitable raid targets in your war range",
        "long": (
            "Launches an interactive wizard that walks you through 6–8 filter stages "
            "to find the best raid targets:\n"
            "1. **Re-use previous config** (if available)\n"
            "2. **Presentation** — Discord embed, text message, or a full interactive webpage\n"
            "3. **Scope** — all nations, applicants & allianceless, or only allianceless\n"
            "4. **Max defensive wars** — 0, 1, 2, or 3\n"
            "5. **Inactivity** — no filter, 7+, 14+, or 30+ days inactive\n"
            "6. **Beige** — include or exclude beige nations\n"
            "7. **Minimum previous beige loot** — $0, $5m, $10m, or $20m\n"
            "8. **Performance filter** — hide targets with negative income, strong ground, or $0 loot\n\n"
            "Your filter choices are saved so you can re-use them next time. "
            "The server's Do Not Raid (DNR) list is automatically respected."
        ),
        "parameters": {
            "score": (
                "Override the score used to calculate your war range. "
                "If omitted, your actual nation score is used. "
                "War range is 0.75× to 2.5× the score."
            ),
        },
        "examples": [
            "`/raids` — use your current score",
            "`/raids 3500` — pretend your score is 3500",
        ],
        "notes": (
            "The webpage option gives the richest view with sortable columns. "
            "The embed option lets you page through targets and set beige reminders. "
            "Use `/config dnr` to set a server-wide Do Not Raid list."
        ),
    },
    "reminders show": {
        "short": "View all your active beige exit reminders",
        "long": (
            "Displays a list of every nation you've set a beige exit reminder for, "
            "with the estimated exit timestamp and a live countdown. Paginates "
            "automatically if you have more than 20 reminders."
        ),
        "parameters": {},
        "examples": ["`/reminders show`"],
    },
    "reminders delete": {
        "short": "Remove a beige reminder for a specific nation",
        "long": (
            "Deletes one of your beige exit reminders so you'll no longer be notified "
            "when that nation leaves beige."
        ),
        "parameters": {
            "nation": (
                "The nation to stop tracking. Accepts a nation name, nation ID, "
                "nation link, or Discord username."
            ),
        },
        "examples": [
            "`/reminders delete 12345`",
            "`/reminders delete Borg`",
        ],
    },
    "reminders add": {
        "short": "Get notified when a nation exits beige or VM",
        "long": (
            "Adds a beige exit reminder for the specified nation. When their beige "
            "or vacation mode is about to expire, you'll receive a DM at the times "
            "you configured with `/config reminders` (default: 15 minutes before). "
            "The nation must currently be in beige or vacation mode."
        ),
        "parameters": {
            "nation": (
                "The nation to track. Accepts a nation name, nation ID, "
                "nation link, or Discord username."
            ),
        },
        "examples": [
            "`/reminders add 12345`",
            "`/reminders add Borg`",
        ],
        "notes": "Use `/config reminders` to customize *when* you get notified.",
    },
    "battlesimulation": {
        "short": "Simulate ground, air, and naval battles between two nations",
        "long": (
            "Calculates win probabilities (Immense Triumph, Moderate Success, Pyrrhic "
            "Victory, Utter Failure) for ground, air, and naval combat between two "
            "nations. Also shows expected casualty ranges for each battle type. "
            "Includes a button to swap attacker/defender perspective and a link to "
            "the detailed damage calculator webpage.\n\n"
            "If used inside a war coordination thread whose name contains a nation ID "
            "in parentheses, the enemy nation is auto-detected."
        ),
        "parameters": {
            "nation1": (
                "The first nation (attacker). Accepts nation name, leader name, "
                "nation ID, nation link, or Discord username. Defaults to your nation."
            ),
            "nation2": (
                "The second nation (defender). Same formats as nation1. "
                "Defaults to your nation if only one is provided."
            ),
        },
        "examples": [
            "`/battlesimulation` — your nation vs. yourself (useful for seeing your own stats)",
            "`/battlesimulation 12345 67890` — nation #12345 attacks #67890",
            "`/battlesimulation @SomeUser` — that user attacks you",
        ],
    },
    "war_status": {
        "short": "Get a detailed overview of a nation's ongoing wars",
        "long": (
            "Shows a rich dashboard of all active wars for a nation with three "
            "switchable tabs:\n"
            "• **General** — resistance bars, MAPs, war expiration, IT chances\n"
            "• **Military** — troop counts, war slots, nukes & missiles\n"
            "• **Damage** — average net damage per MAP for every attack type\n\n"
            "If used inside a war thread whose name contains a nation ID in "
            "parentheses, the target nation is auto-detected."
        ),
        "parameters": {
            "nation": (
                "The nation to inspect. Accepts nation name, nation ID, nation link, "
                "or Discord username. Defaults to your nation or the thread target."
            ),
        },
        "examples": [
            "`/war_status` — your own wars (or thread target)",
            "`/war_status 12345` — wars of nation #12345",
            "`/war_status @SomeUser` — wars of a Discord user's nation",
        ],
    },
    "nuketargets": {
        "short": "Find high-infra nations to nuke or missile in your range",
        "long": (
            "Scans nations within your war range and ranks them by the dollar damage "
            "a nuke or missile would inflict. Shows damage per nuke, damage per missile, "
            "max and average infrastructure, and whether they have Iron Dome or Vital "
            "Defense System.\n\n"
            "By default, targets are limited to alliances configured via `/config` for "
            "this server. If none are configured, you can choose to target all nations. "
            "Beige/VM nations and fully-slotted nations are excluded by default."
        ),
        "parameters": {
            "sort": (
                "Which metric to rank by: `Nuke damage` or `Missile damage`. "
                "Defaults to `Nuke damage`."
            ),
            "include_beige": "Include beige and vacation-mode nations. Defaults to False.",
            "include_slotted": (
                "Include nations already in your wars or with 3 defensive wars. "
                "Defaults to False."
            ),
        },
        "examples": [
            "`/nuketargets` — top nuke targets with default filters",
            '`/nuketargets "Missile damage"` — sorted by missile damage',
            "`/nuketargets True True` — include beige and slotted nations",
        ],
        "notes": "Server admins should use `/config` to set target alliances for best results.",
    },
    "damage": {
        "short": "View full damage calculations between two nations",
        "long": (
            "Generates a link to the damage calculator webpage showing a complete "
            "breakdown of every attack type (ground, air, naval, missiles, nukes) "
            "between two nations, including infrastructure destruction, resource "
            "losses, and loot estimates.\n\n"
            "If used inside a war thread whose name contains a nation ID in "
            "parentheses, the enemy nation is auto-detected."
        ),
        "parameters": {
            "nation1": (
                "The attacking nation. Accepts nation name, leader name, nation ID, "
                "nation link, or Discord username. Defaults to your nation."
            ),
            "nation2": (
                "The defending nation. Same formats. "
                "Defaults to your nation if only one is provided."
            ),
        },
        "examples": [
            "`/damage 12345 67890` — damage when #12345 attacks #67890",
            "`/damage @SomeUser` — damage when that user attacks you",
        ],
    },

    # ── Config Commands ───────────────────────────────────────────────
    "config dnr": {
        "short": "Set the Do Not Raid alliance list for this server",
        "long": (
            "Configures which alliances are excluded from `/raids` results in this "
            "server. Nations belonging to DNR alliances will never appear as raid "
            "targets. Run the command with no IDs to clear the list.\n\n"
            "Requires the **Manage Server** permission."
        ),
        "parameters": {
            "alliance_ids": (
                "Comma-separated alliance IDs to set as the DNR list "
                "(e.g. `770,1234,5678`). Leave empty to clear."
            ),
        },
        "examples": [
            "`/config dnr 770,1234` — protect alliances 770 and 1234",
            "`/config dnr` — clear the DNR list",
        ],
    },
    "config view_current_settings": {
        "short": "View this server's current Autolycus configuration",
        "long": (
            "Displays all configured settings for this server including the DNR list, "
            "target alliances, and any other server-specific options. The response is "
            "ephemeral (only visible to you).\n\n"
            "Requires the **Manage Server** permission."
        ),
        "parameters": {},
        "examples": ["`/config view_current_settings`"],
    },
    "config reminders": {
        "short": "Customize when you receive beige exit reminder DMs",
        "long": (
            "Opens an interactive wizard to set up multiple reminder times for beige "
            "exit notifications. For example, you can be notified 30 minutes, "
            "15 minutes, and 5 minutes before a tracked nation exits beige.\n\n"
            "You can keep your existing reminders and add more, or discard them "
            "and start fresh. If you finish without adding any, the system default "
            "of 15 minutes will be used.\n\n"
            "Requires the **Manage Server** permission."
        ),
        "parameters": {},
        "examples": ["`/config reminders`"],
        "notes": "This configures *when* you get reminded. Use `/reminders add` to track a nation.",
    },

    # ── Help ──────────────────────────────────────────────────────────
    "help": {
        "short": "Show all commands or get detailed help for one",
        "long": (
            "Without arguments, displays a compact list of every command with its "
            "short description. Provide a command name to see its full description, "
            "parameter definitions, and usage examples."
        ),
        "parameters": {
            "command": (
                "The name of a specific command to get detailed help for "
                "(e.g. `raids`, `revenue nation`, `config dnr`). "
                "Autocomplete is supported."
            ),
        },
        "examples": [
            "`/help` — list all commands",
            "`/help raids` — detailed help for /raids",
            "`/help revenue nation` — detailed help for /revenue nation",
        ],
    },
}


def get_all_command_names() -> List[str]:
    """Return a sorted list of all registered command names."""
    return sorted(COMMAND_HELP.keys())


def get_help(command_name: str) -> Optional[CommandHelp]:
    """Retrieve help metadata for a command by name.
    
    Args:
        command_name: The slash command name (e.g. 'raids', 'revenue nation').
        
    Returns:
        The CommandHelp dict if found, else None.
    """
    return COMMAND_HELP.get(command_name)
