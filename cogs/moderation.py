import os
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import discord
from discord.ext import commands
from discord import app_commands


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _log_channel_id() -> int | None:
    raw = os.getenv("LOG_CHANNEL_ID", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _load_log_channel_id(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = data.get("log_channel_id")
    if isinstance(value, int):
        return value
    return None


def _save_log_channel_id(path: Path, channel_id: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"log_channel_id": channel_id}
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _load_whitelist(path: Path) -> set[int]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    ids = data.get("whitelist", [])
    if not isinstance(ids, list):
        return set()
    return {int(x) for x in ids if isinstance(x, int) or str(x).isdigit()}


def _save_whitelist(path: Path, whitelist: set[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"whitelist": sorted(whitelist)}
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _can_moderate(ctx: commands.Context) -> bool:
    perms = ctx.author.guild_permissions
    return perms.ban_members or perms.kick_members


def _app_can_moderate(interaction: discord.Interaction) -> bool:
    if not interaction.guild or not interaction.user:
        return False
    perms = interaction.user.guild_permissions
    return perms.ban_members or perms.kick_members


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.ban_under_days = _int_env("BAN_UNDER_DAYS", 7)
        self.kick_under_days = _int_env("KICK_UNDER_DAYS", 30)
        self.config_path = Path("data") / "log_channel.json"
        self.whitelist_path = Path("data") / "whitelist.json"
        self.log_channel_id = _load_log_channel_id(self.config_path) or _log_channel_id()
        self.whitelist = _load_whitelist(self.whitelist_path)
        self.app_whitelist = app_commands.Group(
            name="whitelist", description="Quản lý whitelist"
        )
        self.app_whitelist.add_command(self._app_whitelist_add)
        self.app_whitelist.add_command(self._app_whitelist_remove)
        self.app_whitelist.add_command(self._app_whitelist_list)
        self.bot.tree.add_command(self.app_whitelist)

    def _embed(self, title: str, description: str, color: int) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=color)

    async def _log(self, guild: discord.Guild, embed: discord.Embed) -> None:
        if not self.log_channel_id:
            return
        channel = guild.get_channel(self.log_channel_id)
        if isinstance(channel, discord.TextChannel):
            await channel.send(embed=embed)

    @commands.hybrid_command(name="setlog")
    @commands.has_permissions(manage_guild=True)
    async def set_log_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
        self.log_channel_id = channel.id
        _save_log_channel_id(self.config_path, channel.id)
        embed = self._embed(
            "Log Channel Set",
            f"Log channel set to {channel.mention}.",
            0x3B82F6,
        )
        await ctx.send(embed=embed)

    @commands.group(name="whitelist", invoke_without_command=True)
    async def whitelist_group(self, ctx: commands.Context) -> None:
        if not _can_moderate(ctx):
            await ctx.send(
                embed=self._embed(
                    "Permission Required",
                    "You need ban or kick permissions to use this command.",
                    0xEF4444,
                )
            )
            return
        if not self.whitelist:
            await ctx.send(
                embed=self._embed("Whitelist", "Whitelist is empty.", 0x64748B)
            )
            return
        ids = ", ".join(str(x) for x in sorted(self.whitelist))
        await ctx.send(
            embed=self._embed("Whitelist IDs", ids, 0x64748B)
        )

    @whitelist_group.command(name="add")
    async def whitelist_add(self, ctx: commands.Context, user_id: int) -> None:
        if not _can_moderate(ctx):
            await ctx.send(
                embed=self._embed(
                    "Permission Required",
                    "You need ban or kick permissions to use this command.",
                    0xEF4444,
                )
            )
            return
        self.whitelist.add(user_id)
        _save_whitelist(self.whitelist_path, self.whitelist)
        await ctx.send(
            embed=self._embed(
                "Whitelist Updated",
                f"Added `{user_id}` to whitelist.",
                0x22C55E,
            )
        )

    @whitelist_group.command(name="remove")
    async def whitelist_remove(self, ctx: commands.Context, user_id: int) -> None:
        if not _can_moderate(ctx):
            await ctx.send(
                embed=self._embed(
                    "Permission Required",
                    "You need ban or kick permissions to use this command.",
                    0xEF4444,
                )
            )
            return
        if user_id in self.whitelist:
            self.whitelist.remove(user_id)
            _save_whitelist(self.whitelist_path, self.whitelist)
            await ctx.send(
                embed=self._embed(
                    "Whitelist Updated",
                    f"Removed `{user_id}` from whitelist.",
                    0xF59E0B,
                )
            )
        else:
            await ctx.send(
                embed=self._embed(
                    "Whitelist",
                    "This ID is not in the whitelist.",
                    0x64748B,
                )
            )

    @whitelist_group.command(name="list")
    async def whitelist_list(self, ctx: commands.Context) -> None:
        if not _can_moderate(ctx):
            await ctx.send(
                embed=self._embed(
                    "Permission Required",
                    "You need ban or kick permissions to use this command.",
                    0xEF4444,
                )
            )
            return
        if not self.whitelist:
            await ctx.send(
                embed=self._embed("Whitelist", "Whitelist is empty.", 0x64748B)
            )
            return
        ids = ", ".join(str(x) for x in sorted(self.whitelist))
        await ctx.send(embed=self._embed("Whitelist IDs", ids, 0x64748B))

    @app_commands.command(name="add", description="Thêm user vào whitelist")
    @app_commands.check(_app_can_moderate)
    async def _app_whitelist_add(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        self.whitelist.add(user.id)
        _save_whitelist(self.whitelist_path, self.whitelist)
        await interaction.response.send_message(
            embed=self._embed(
                "Whitelist Updated",
                f"Added {user} (ID: {user.id}) to whitelist.",
                0x22C55E,
            ),
            ephemeral=True,
        )

    @app_commands.command(name="remove", description="Xóa user khỏi whitelist")
    @app_commands.check(_app_can_moderate)
    async def _app_whitelist_remove(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        if user.id in self.whitelist:
            self.whitelist.remove(user.id)
            _save_whitelist(self.whitelist_path, self.whitelist)
            await interaction.response.send_message(
                embed=self._embed(
                    "Whitelist Updated",
                    f"Removed {user} (ID: {user.id}) from whitelist.",
                    0xF59E0B,
                ),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=self._embed(
                    "Whitelist",
                    "This user is not in the whitelist.",
                    0x64748B,
                ),
                ephemeral=True,
            )

    @app_commands.command(name="list", description="Xem danh sách whitelist")
    @app_commands.check(_app_can_moderate)
    async def _app_whitelist_list(self, interaction: discord.Interaction) -> None:
        if not self.whitelist:
            await interaction.response.send_message(
                embed=self._embed("Whitelist", "Whitelist is empty.", 0x64748B),
                ephemeral=True,
            )
            return
        ids = ", ".join(str(x) for x in sorted(self.whitelist))
        await interaction.response.send_message(
            embed=self._embed("Whitelist IDs", ids, 0x64748B), ephemeral=True
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        # Skip bots
        if member.bot:
            return
        # Skip whitelisted IDs
        if member.id in self.whitelist:
            return

        now = datetime.now(timezone.utc)
        age = now - member.created_at
        created_at = member.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d")

        ban_delta = timedelta(days=self.ban_under_days)
        kick_delta = timedelta(days=self.kick_under_days)

        try:
            if age < ban_delta:
                reason = (
                    f"Account age {age.days}d < {self.ban_under_days}d "
                    f"(Created: {created_at} UTC)"
                )
                try:
                    await member.send(
                        embed=self._embed(
                            "Banned",
                            f"You were banned from {member.guild.name}.\nReason: {reason}",
                            0xEF4444,
                        )
                    )
                except discord.HTTPException:
                    pass
                await member.ban(reason=reason)
                await self._log(
                    member.guild,
                    self._embed(
                        "User Banned",
                        f"{member} (ID: {member.id})\nReason: {reason}",
                        0xEF4444,
                    ),
                )
                return

            if age < kick_delta:
                reason = (
                    f"Account age {age.days}d < {self.kick_under_days}d "
                    f"(Created: {created_at} UTC)"
                )
                try:
                    await member.send(
                        embed=self._embed(
                            "Kicked",
                            f"You were kicked from {member.guild.name}.\nReason: {reason}",
                            0xF59E0B,
                        )
                    )
                except discord.HTTPException:
                    pass
                await member.kick(reason=reason)
                await self._log(
                    member.guild,
                    self._embed(
                        "User Kicked",
                        f"{member} (ID: {member.id})\nReason: {reason}",
                        0xF59E0B,
                    ),
                )
        except discord.Forbidden:
            await self._log(
                member.guild,
                self._embed(
                    "Permission Error",
                    f"Missing permissions to moderate {member} (ID: {member.id}).",
                    0xEF4444,
                ),
            )
        except discord.HTTPException as exc:
            await self._log(
                member.guild,
                self._embed(
                    "Moderation Error",
                    f"Failed to moderate {member} (ID: {member.id}): {exc}",
                    0xEF4444,
                ),
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
