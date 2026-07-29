"""User-safe error embeds, memorable reference passphrases, and operator logging."""

from __future__ import annotations

import logging
import os
import traceback
import discord
import xkcdpass.xkcd_password as xp
from discord.ext import commands
from bot.discord_utils.embeds import DEFAULT_CONTACT_FOOTER

ERROR_EMBED_COLOR = 0xED4245
PNW_SERVER_USER_MESSAGE = (
    "Politics & War's server is currently having issues. "
    "Please wait a bit and try again once PnW resolves it."
)

_wordfile = xp.locate_wordfile()
_WORDLIST = xp.generate_wordlist(wordfile=_wordfile, min_length=3, max_length=9)


def new_error_reference() -> str:
    """Memorable hyphenated passphrase for correlating user, logs, and debug channel."""
    return xp.generate_xkcdpassword(_WORDLIST, numwords=4, delimiter="-", interactive=False, acrostic=False)


def unwrap_command_error(error: BaseException) -> BaseException:
    if isinstance(error, discord.errors.ApplicationCommandInvokeError):
        return error.original
    if isinstance(error, commands.CommandInvokeError) and error.original:
        return error.original
    return error


def is_pnw_server_error(error: BaseException) -> bool:
    root = unwrap_command_error(error)
    if type(root).__name__ == "PnWServerError":
        return True
    msg = str(root).lower()
    return "internal server error" in msg or "pnw server error" in msg


def error_embed(
    title: str,
    description: str,
    *,
    reference: str | None = None,
    color: int = ERROR_EMBED_COLOR,
    contact_footer: str | None = DEFAULT_CONTACT_FOOTER,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    footer_parts: list[str] = []
    if reference:
        footer_parts.append(f"Reference: {reference}")
    if contact_footer:
        footer_parts.append(contact_footer)
    if footer_parts:
        embed.set_footer(text="\n".join(footer_parts)[:2048])
    return embed


def log_command_error(
    logger: logging.Logger,
    exc: BaseException,
    *,
    ctx: discord.ApplicationContext,
    reference: str,
    command_name: str | None = None,
) -> None:
    cmd = command_name
    if cmd is None and ctx.command is not None:
        cmd = getattr(ctx.command, "qualified_name", None) or ctx.command.name
    cmd = cmd or "?"
    guild_id = ctx.guild.id if ctx.guild else None
    # Always pass the explicit traceback tuple so stack traces are preserved
    # even when logging from handled paths (not just inside active except blocks).
    logger.error(
        "command_error reference=%r command=%s user_id=%s guild_id=%s channel_id=%s",
        reference,
        cmd,
        ctx.author.id,
        guild_id,
        ctx.channel_id,
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"error_reference": reference},
    )


def _format_traceback_text(error: BaseException) -> str:
    root = unwrap_command_error(error)
    lines = traceback.format_exception(type(root), root, root.__traceback__)
    return "".join(lines).replace("```", "'''")


def build_debug_embed(
    ctx: discord.ApplicationContext,
    error: BaseException,
    reference: str,
) -> discord.Embed:
    root = unwrap_command_error(error)
    guild_label = f"{ctx.guild.name} ({ctx.guild.id})" if ctx.guild else "DM"
    author_label = f"{ctx.author} ({ctx.author.id})"
    cmd_label = str(ctx.command) if ctx.command else "?"
    err_preview = repr(root)
    if len(err_preview) > 900:
        err_preview = err_preview[:897] + "..."

    embed = discord.Embed(
        title=f"Error — {reference}",
        color=ERROR_EMBED_COLOR,
    )
    embed.add_field(name="Reference", value=reference[:1024], inline=False)
    embed.add_field(name="Command", value=cmd_label[:1024], inline=False)
    embed.add_field(name="User", value=author_label[:1024], inline=False)
    embed.add_field(name="Guild", value=guild_label[:1024], inline=False)
    embed.add_field(name="Type", value=type(root).__name__[:1024], inline=False)
    embed.add_field(name="Summary", value=f"```{err_preview}```"[:1024], inline=False)
    return embed


def chunk_text_for_discord(text: str, max_len: int = 1900) -> list[str]:
    """Split long text on newlines for ``` code blocks under message length limits."""
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for line in text.split("\n"):
        line_len = len(line) + 1
        if cur_len + line_len > max_len and cur:
            chunks.append("\n".join(cur))
            cur = [line]
            cur_len = line_len
        else:
            cur.append(line)
            cur_len += line_len
    if cur:
        chunks.append("\n".join(cur))
    return chunks


async def safe_reply_error(
    ctx: discord.ApplicationContext,
    embed: discord.Embed,
    *,
    ephemeral: bool = True,
    reference: str,
    log: logging.Logger,
) -> None:
    try:
        if ctx.interaction.response.is_done():
            await ctx.followup.send(embed=embed, ephemeral=ephemeral)
        else:
            await ctx.respond(embed=embed, ephemeral=ephemeral)
    except (discord.HTTPException, discord.NotFound) as send_exc:
        log.error(
            "failed_to_send_user_error reference=%r: %s",
            reference,
            send_exc,
            exc_info=send_exc,
            extra={"error_reference": reference},
        )


async def send_debug_channel_messages(
    channel: discord.abc.Messageable | None,
    ctx: discord.ApplicationContext,
    error: BaseException,
    reference: str,
    log: logging.Logger,
) -> None:
    await send_embed_with_trace_thread(
        channel,
        embed=build_debug_embed(ctx, error, reference),
        traceback_text=_format_traceback_text(error),
        log=log,
        thread_name=f"trace-{reference}",
        reference=reference,
    )


async def send_embed_with_trace_thread(
    channel: discord.abc.Messageable | None,
    *,
    embed: discord.Embed,
    traceback_text: str,
    log: logging.Logger,
    thread_name: str,
    reference: str | None = None,
) -> None:
    if channel is None:
        return
    try:
        message = await channel.send(embed=embed)
        trace_target: discord.abc.Messageable = channel
        if isinstance(channel, discord.TextChannel):
            try:
                trace_target = await message.create_thread(
                    name=thread_name[:100],
                    auto_archive_duration=1440,
                )
            except (discord.HTTPException, discord.Forbidden, TypeError) as thread_exc:
                if reference:
                    log.warning(
                        "Failed to create traceback thread reference=%r: %s",
                        reference,
                        thread_exc,
                    )
                else:
                    log.warning(
                        "Failed to create traceback thread: %s",
                        thread_exc,
                    )
        chunks = chunk_text_for_discord(
            traceback_text.replace("```", "'''"),
            max_len=1700,
        )
        for chunk in chunks:
            await trace_target.send(f"```{chunk}\n```")
    except (discord.HTTPException, discord.NotFound, TypeError) as e:
        if reference:
            log.error(
                "failed_debug_channel reference=%r: %s",
                reference,
                e,
                exc_info=e,
                extra={"error_reference": reference},
            )
        else:
            log.error("failed_debug_channel: %s", e, exc_info=e)


def _resolve_debug_channel(bot: discord.Client) -> discord.abc.Messageable | None:
    channel_id_raw = os.getenv("DEBUG_CHANNEL")
    if not channel_id_raw:
        return None
    try:
        return bot.get_channel(int(channel_id_raw))
    except (TypeError, ValueError):
        return None


async def report_handled_exception(
    bot: commands.Bot,
    ctx: discord.ApplicationContext,
    error: BaseException,
    log: logging.Logger,
    *,
    reference: str | None = None,
    command_name: str | None = None,
) -> str:
    """
    Log and forward a handled exception to the configured debug channel.
    Returns the reference used for this error.
    """
    ref = reference or new_error_reference()
    root = unwrap_command_error(error)
    log_command_error(log, root, ctx=ctx, reference=ref, command_name=command_name)
    await send_debug_channel_messages(_resolve_debug_channel(bot), ctx, error, ref, log)
    return ref


async def report_bot_exception(
    bot: discord.Client | None,
    error: BaseException,
    log: logging.Logger,
    *,
    reference: str | None = None,
    title: str = "Bot error",
    details: str | None = None,
) -> str:
    """
    Log a bot-side exception and forward it to the configured debug channel.
    Use for non-command paths (e.g. interaction handlers) that still have a bot instance.
    """
    ref = reference or new_error_reference()
    root = unwrap_command_error(error)
    log.error(
        "bot_error reference=%r title=%r: %s",
        ref,
        title,
        root,
        exc_info=(type(root), root, root.__traceback__),
        extra={"error_reference": ref},
    )
    if bot is None:
        return ref

    embed = error_embed(
        f"{title} — {ref}",
        details or f"```{repr(root)[:900]}```",
        reference=ref,
        contact_footer=None,
    )
    embed.add_field(name="Type", value=type(root).__name__[:1024], inline=False)
    await send_embed_with_trace_thread(
        _resolve_debug_channel(bot),
        embed=embed,
        traceback_text=_format_traceback_text(error),
        log=log,
        thread_name=f"trace-{ref}",
        reference=ref,
    )
    return ref
