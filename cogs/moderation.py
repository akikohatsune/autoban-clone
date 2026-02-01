import os
import json
import sqlite3
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


def _db_path() -> Path:
    path = Path("data") / "whitelist.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _init_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS whitelist (user_id INTEGER PRIMARY KEY)"
        )
        conn.commit()


def _whitelist_all(path: Path) -> list[int]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT user_id FROM whitelist ORDER BY user_id").fetchall()
    return [int(r[0]) for r in rows]


def _whitelist_has(path: Path, user_id: int) -> bool:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT 1 FROM whitelist WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
    return row is not None


def _whitelist_add(path: Path, user_id: int) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO whitelist (user_id) VALUES (?)", (user_id,)
        )
        conn.commit()


def _whitelist_remove(path: Path, user_id: int) -> bool:
    with sqlite3.connect(path) as conn:
        cur = conn.execute("DELETE FROM whitelist WHERE user_id = ?", (user_id,))
        conn.commit()
    return cur.rowcount > 0


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
        self.log_channel_id = _load_log_channel_id(self.config_path) or _log_channel_id()
        self.whitelist_db = _db_path()
        _init_db(self.whitelist_db)
        self.app_whitelist = app_commands.Group(
            name="whitelist", description="ホワイトリスト管理 / Manage whitelist"
        )
        self.app_whitelist.add_command(self._app_whitelist_add)
        self.app_whitelist.add_command(self._app_whitelist_remove)
        self.app_whitelist.add_command(self._app_whitelist_list)
        if not self.bot.tree.get_command("whitelist"):
            self.bot.tree.add_command(self.app_whitelist)

    def _embed(self, title: str, description: str, color: int) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=color)

    async def _log(self, guild: discord.Guild, embed: discord.Embed) -> None:
        if not self.log_channel_id:
            return
        channel = guild.get_channel(self.log_channel_id)
        if isinstance(channel, discord.TextChannel):
            await channel.send(embed=embed)

    async def cog_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(
                embed=self._embed(
                    "権限が必要 / Permission Required",
                    "このコマンドを使うには必要な権限がありません。\nYou do not have the required permissions for this command.",
                    0xEF4444,
                )
            )

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self._embed(
                        "権限が必要 / Permission Required",
                        "このコマンドを使うには必要な権限がありません。\nYou do not have the required permissions for this command.",
                        0xEF4444,
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=self._embed(
                        "権限が必要 / Permission Required",
                        "このコマンドを使うには必要な権限がありません。\nYou do not have the required permissions for this command.",
                        0xEF4444,
                    ),
                    ephemeral=True,
                )

    @commands.hybrid_command(name="setlog")
    @commands.has_permissions(manage_guild=True)
    async def set_log_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
        self.log_channel_id = channel.id
        _save_log_channel_id(self.config_path, channel.id)
        embed = self._embed(
            "ログチャンネル設定 / Log Channel Set",
            f"ログチャンネルを {channel.mention} に設定しました。\nLog channel set to {channel.mention}.",
            0x3B82F6,
        )
        await ctx.send(embed=embed)

    @commands.group(name="whitelist", invoke_without_command=True)
    async def whitelist_group(self, ctx: commands.Context) -> None:
        if not _can_moderate(ctx):
            await ctx.send(
                embed=self._embed(
                    "権限が必要 / Permission Required",
                    "このコマンドを使うにはBANまたはKICK権限が必要です。\nYou need ban or kick permissions to use this command.",
                    0xEF4444,
                )
            )
            return
        ids = _whitelist_all(self.whitelist_db)
        if not ids:
            await ctx.send(
                embed=self._embed(
                    "ホワイトリスト / Whitelist",
                    "ホワイトリストは空です。\nWhitelist is empty.",
                    0x64748B,
                )
            )
            return
        ids = ", ".join(str(x) for x in ids)
        await ctx.send(
            embed=self._embed(
                "ホワイトリストID / Whitelist IDs",
                f"{ids}",
                0x64748B,
            )
        )

    @whitelist_group.command(name="add")
    async def whitelist_add(self, ctx: commands.Context, user_id: int) -> None:
        if not _can_moderate(ctx):
            await ctx.send(
                embed=self._embed(
                    "権限が必要 / Permission Required",
                    "このコマンドを使うにはBANまたはKICK権限が必要です。\nYou need ban or kick permissions to use this command.",
                    0xEF4444,
                )
            )
            return
        _whitelist_add(self.whitelist_db, user_id)
        await ctx.send(
            embed=self._embed(
                "ホワイトリスト更新 / Whitelist Updated",
                f"ホワイトリストに `{user_id}` を追加しました。\nAdded `{user_id}` to whitelist.",
                0x22C55E,
            )
        )

    @whitelist_group.command(name="remove")
    async def whitelist_remove(self, ctx: commands.Context, user_id: int) -> None:
        if not _can_moderate(ctx):
            await ctx.send(
                embed=self._embed(
                    "権限が必要 / Permission Required",
                    "このコマンドを使うにはBANまたはKICK権限が必要です。\nYou need ban or kick permissions to use this command.",
                    0xEF4444,
                )
            )
            return
        if _whitelist_remove(self.whitelist_db, user_id):
            await ctx.send(
                embed=self._embed(
                    "ホワイトリスト更新 / Whitelist Updated",
                    f"ホワイトリストから `{user_id}` を削除しました。\nRemoved `{user_id}` from whitelist.",
                    0xF59E0B,
                )
            )
        else:
            await ctx.send(
                embed=self._embed(
                    "ホワイトリスト / Whitelist",
                    "このIDはホワイトリストにありません。\nThis ID is not in the whitelist.",
                    0x64748B,
                )
            )

    @whitelist_group.command(name="list")
    async def whitelist_list(self, ctx: commands.Context) -> None:
        if not _can_moderate(ctx):
            await ctx.send(
                embed=self._embed(
                    "権限が必要 / Permission Required",
                    "このコマンドを使うにはBANまたはKICK権限が必要です。\nYou need ban or kick permissions to use this command.",
                    0xEF4444,
                )
            )
            return
        ids = _whitelist_all(self.whitelist_db)
        if not ids:
            await ctx.send(
                embed=self._embed(
                    "ホワイトリスト / Whitelist",
                    "ホワイトリストは空です。\nWhitelist is empty.",
                    0x64748B,
                )
            )
            return
        ids = ", ".join(str(x) for x in ids)
        await ctx.send(
            embed=self._embed(
                "ホワイトリストID / Whitelist IDs",
                f"{ids}",
                0x64748B,
            )
        )

    @app_commands.command(name="add", description="ユーザーを追加 / Add user")
    @app_commands.check(_app_can_moderate)
    async def _app_whitelist_add(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        _whitelist_add(self.whitelist_db, user.id)
        await interaction.response.send_message(
            embed=self._embed(
                "ホワイトリスト更新 / Whitelist Updated",
                f"ホワイトリストに {user} (ID: {user.id}) を追加しました。\nAdded {user} (ID: {user.id}) to whitelist.",
                0x22C55E,
            ),
            ephemeral=True,
        )

    @app_commands.command(name="remove", description="ユーザーを削除 / Remove user")
    @app_commands.check(_app_can_moderate)
    async def _app_whitelist_remove(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        if _whitelist_remove(self.whitelist_db, user.id):
            await interaction.response.send_message(
                embed=self._embed(
                    "ホワイトリスト更新 / Whitelist Updated",
                    f"ホワイトリストから {user} (ID: {user.id}) を削除しました。\nRemoved {user} (ID: {user.id}) from whitelist.",
                    0xF59E0B,
                ),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=self._embed(
                    "ホワイトリスト / Whitelist",
                    "このユーザーはホワイトリストにありません。\nThis user is not in the whitelist.",
                    0x64748B,
                ),
                ephemeral=True,
            )

    @app_commands.command(name="list", description="一覧表示 / List whitelist")
    @app_commands.check(_app_can_moderate)
    async def _app_whitelist_list(self, interaction: discord.Interaction) -> None:
        ids = _whitelist_all(self.whitelist_db)
        if not ids:
            await interaction.response.send_message(
                embed=self._embed(
                    "ホワイトリスト / Whitelist",
                    "ホワイトリストは空です。\nWhitelist is empty.",
                    0x64748B,
                ),
                ephemeral=True,
            )
            return
        ids = ", ".join(str(x) for x in ids)
        await interaction.response.send_message(
            embed=self._embed(
                "ホワイトリストID / Whitelist IDs",
                f"{ids}",
                0x64748B,
            ),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        # Skip bots
        if member.bot:
            return
        # Skip whitelisted IDs
        if _whitelist_has(self.whitelist_db, member.id):
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
                            "BANされました / Banned",
                            f"{member.guild.name} からBANされました。\n理由: {reason}\nYou were banned from {member.guild.name}.\nReason: {reason}",
                            0xEF4444,
                        )
                    )
                except discord.HTTPException:
                    pass
                await member.ban(reason=reason)
                await self._log(
                    member.guild,
                    self._embed(
                        "ユーザーBAN / User Banned",
                        f"{member} (ID: {member.id})\n理由: {reason}\nReason: {reason}",
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
                            "KICKされました / Kicked",
                            f"{member.guild.name} からKICKされました。\n理由: {reason}\nYou were kicked from {member.guild.name}.\nReason: {reason}",
                            0xF59E0B,
                        )
                    )
                except discord.HTTPException:
                    pass
                await member.kick(reason=reason)
                await self._log(
                    member.guild,
                    self._embed(
                        "ユーザーKICK / User Kicked",
                        f"{member} (ID: {member.id})\n理由: {reason}\nReason: {reason}",
                        0xF59E0B,
                    ),
                )
        except discord.Forbidden:
            await self._log(
                member.guild,
                self._embed(
                    "権限エラー / Permission Error",
                    f"{member} (ID: {member.id}) を処理する権限がありません。\nMissing permissions to moderate {member} (ID: {member.id}).",
                    0xEF4444,
                ),
            )
        except discord.HTTPException as exc:
            await self._log(
                member.guild,
                self._embed(
                    "モデレーションエラー / Moderation Error",
                    f"{member} (ID: {member.id}) の処理に失敗しました: {exc}\nFailed to moderate {member} (ID: {member.id}): {exc}",
                    0xEF4444,
                ),
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
