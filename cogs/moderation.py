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


def _settings_db_path() -> Path:
    path = Path("data") / "settings.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _init_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS whitelist (user_id INTEGER PRIMARY KEY)"
        )
        conn.commit()


def _init_settings_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings ("
            "guild_id INTEGER PRIMARY KEY,"
            "ban_under_days INTEGER NOT NULL,"
            "kick_under_days INTEGER NOT NULL,"
            "ban_under_seconds INTEGER,"
            "kick_under_seconds INTEGER"
            ")"
        )
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(settings)").fetchall()
        }
        if "ban_under_seconds" not in columns:
            conn.execute("ALTER TABLE settings ADD COLUMN ban_under_seconds INTEGER")
        if "kick_under_seconds" not in columns:
            conn.execute("ALTER TABLE settings ADD COLUMN kick_under_seconds INTEGER")
        if "ban_under_days" not in columns:
            conn.execute("ALTER TABLE settings ADD COLUMN ban_under_days INTEGER")
        if "kick_under_days" not in columns:
            conn.execute("ALTER TABLE settings ADD COLUMN kick_under_days INTEGER")
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


def _settings_get(
    path: Path, guild_id: int, default_ban_seconds: int, default_kick_seconds: int
) -> tuple[int, int]:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT ban_under_seconds, kick_under_seconds, ban_under_days, kick_under_days "
            "FROM settings WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()
        if row is not None:
            ban_seconds, kick_seconds, ban_days, kick_days = row
            if ban_seconds is not None and kick_seconds is not None:
                return int(ban_seconds), int(kick_seconds)
            if ban_days is not None and kick_days is not None:
                ban_seconds = int(ban_days) * 86400
                kick_seconds = int(kick_days) * 86400
                conn.execute(
                    "UPDATE settings SET ban_under_seconds = ?, kick_under_seconds = ? "
                    "WHERE guild_id = ?",
                    (ban_seconds, kick_seconds, guild_id),
                )
                conn.commit()
                return ban_seconds, kick_seconds
        conn.execute(
            "INSERT OR IGNORE INTO settings "
            "(guild_id, ban_under_days, kick_under_days, ban_under_seconds, kick_under_seconds)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                guild_id,
                default_ban_seconds // 86400,
                default_kick_seconds // 86400,
                default_ban_seconds,
                default_kick_seconds,
            ),
        )
        conn.commit()
    return default_ban_seconds, default_kick_seconds


def _settings_set(path: Path, guild_id: int, ban_seconds: int, kick_seconds: int) -> None:
    ban_days = (ban_seconds + 86399) // 86400
    kick_days = (kick_seconds + 86399) // 86400
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO settings "
            "(guild_id, ban_under_days, kick_under_days, ban_under_seconds, kick_under_seconds)"
            " VALUES (?, ?, ?, ?, ?)",
            (guild_id, ban_days, kick_days, ban_seconds, kick_seconds),
        )
        conn.execute(
            "UPDATE settings SET ban_under_days = ?, kick_under_days = ?, "
            "ban_under_seconds = ?, kick_under_seconds = ?"
            " WHERE guild_id = ?",
            (ban_days, kick_days, ban_seconds, kick_seconds, guild_id),
        )
        conn.commit()


def _can_moderate(ctx: commands.Context) -> bool:
    perms = ctx.author.guild_permissions
    return perms.ban_members or perms.kick_members


def _app_can_moderate(interaction: discord.Interaction) -> bool:
    if not interaction.guild or not interaction.user:
        return False
    perms = interaction.user.guild_permissions
    return perms.ban_members or perms.kick_members


def _parse_duration(raw: str) -> int | None:
    value = raw.strip().lower()
    if not value:
        return None
    unit = value[-1]
    number = value
    multiplier = 86400
    if unit.isalpha():
        number = value[:-1].strip()
        if unit == "s":
            multiplier = 1
        elif unit == "m":
            multiplier = 60
        elif unit == "h":
            multiplier = 3600
        elif unit == "d":
            multiplier = 86400
        elif unit == "w":
            multiplier = 604800
        else:
            return None
    if not number.isdigit():
        return None
    seconds = int(number) * multiplier
    if seconds < 0:
        return None
    return seconds


def _humanize_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0s"
    remaining = seconds
    parts: list[str] = []
    for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if remaining >= size:
            value = remaining // size
            remaining %= size
            parts.append(f"{value}{unit}")
        if len(parts) >= 2:
            break
    return " ".join(parts)


class Moderation(commands.Cog):
    whitelist_app = app_commands.Group(
        name="whitelist", description="ホワイトリスト管理 / Manage whitelist"
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.default_ban_under_seconds = _int_env("BAN_UNDER_DAYS", 7) * 86400
        self.default_kick_under_seconds = _int_env("KICK_UNDER_DAYS", 30) * 86400
        self.config_path = Path("data") / "log_channel.json"
        self.log_channel_id = _load_log_channel_id(self.config_path) or _log_channel_id()
        self.whitelist_db = _db_path()
        self.settings_db = _settings_db_path()
        _init_db(self.whitelist_db)
        _init_settings_db(self.settings_db)

    def _embed(self, title: str, description: str, color: int) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=color)

    async def _log(self, guild: discord.Guild, embed: discord.Embed) -> None:
        if not self.log_channel_id:
            return
        channel = guild.get_channel(self.log_channel_id)
        if isinstance(channel, discord.TextChannel):
            await channel.send(embed=embed)

    async def _notify_permission_issue(
        self, guild: discord.Guild, member: discord.Member
    ) -> None:
        embed = self._embed(
            "権限エラー / Permission Error",
            (
                f"{member} (ID: {member.id}) を処理できませんでした。\n"
                "BOTのロール位置と権限を確認してください。\n"
                "I could not moderate this member.\n"
                "Please check the bot's role position and permissions."
            ),
            0xEF4444,
        )
        if self.log_channel_id:
            await self._log(guild, embed)
            return
        owner = guild.owner
        if owner is None:
            try:
                owner = await guild.fetch_member(guild.owner_id)
            except (discord.Forbidden, discord.HTTPException):
                owner = None
        if owner is not None:
            try:
                await owner.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

    async def cog_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        if isinstance(error, commands.MissingPermissions) or isinstance(
            error, commands.CheckFailure
        ):
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

    @commands.hybrid_command(name="banday")
    @commands.check(_can_moderate)
    @app_commands.check(_app_can_moderate)
    async def set_ban_days(self, ctx: commands.Context, duration: str) -> None:
        if ctx.guild is None:
            return
        seconds = _parse_duration(duration)
        if seconds is None:
            await ctx.send(
                embed=self._embed(
                    "不正な値 / Invalid Value",
                    (
                        "数値+単位を指定してください (例: 7d, 12h, 30m)。\n"
                        "Please provide a number with unit (e.g. 7d, 12h, 30m)."
                    ),
                    0xEF4444,
                )
            )
            return
        _, kick_seconds = _settings_get(
            self.settings_db,
            ctx.guild.id,
            self.default_ban_under_seconds,
            self.default_kick_under_seconds,
        )
        _settings_set(self.settings_db, ctx.guild.id, seconds, kick_seconds)
        await ctx.send(
            embed=self._embed(
                "BAN時間設定 / Ban Time Set",
                (
                    f"BANの対象時間を `{_humanize_duration(seconds)}` に設定しました。\n"
                    f"Set ban threshold to `{_humanize_duration(seconds)}`."
                ),
                0x22C55E,
            )
        )

    @commands.hybrid_command(name="kickday")
    @commands.check(_can_moderate)
    @app_commands.check(_app_can_moderate)
    async def set_kick_days(self, ctx: commands.Context, duration: str) -> None:
        if ctx.guild is None:
            return
        seconds = _parse_duration(duration)
        if seconds is None:
            await ctx.send(
                embed=self._embed(
                    "不正な値 / Invalid Value",
                    (
                        "数値+単位を指定してください (例: 7d, 12h, 30m)。\n"
                        "Please provide a number with unit (e.g. 7d, 12h, 30m)."
                    ),
                    0xEF4444,
                )
            )
            return
        ban_seconds, _ = _settings_get(
            self.settings_db,
            ctx.guild.id,
            self.default_ban_under_seconds,
            self.default_kick_under_seconds,
        )
        _settings_set(self.settings_db, ctx.guild.id, ban_seconds, seconds)
        await ctx.send(
            embed=self._embed(
                "KICK時間設定 / Kick Time Set",
                (
                    f"KICKの対象時間を `{_humanize_duration(seconds)}` に設定しました。\n"
                    f"Set kick threshold to `{_humanize_duration(seconds)}`."
                ),
                0x22C55E,
            )
        )

    @commands.hybrid_command(name="showday")
    @commands.check(_can_moderate)
    @app_commands.check(_app_can_moderate)
    async def show_days(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return
        ban_seconds, kick_seconds = _settings_get(
            self.settings_db,
            ctx.guild.id,
            self.default_ban_under_seconds,
            self.default_kick_under_seconds,
        )
        await ctx.send(
            embed=self._embed(
                "現在の設定 / Current Settings",
                (
                    f"BAN: `{_humanize_duration(ban_seconds)}`\n"
                    f"KICK: `{_humanize_duration(kick_seconds)}`\n"
                    f"BAN: `{_humanize_duration(ban_seconds)}`\n"
                    f"KICK: `{_humanize_duration(kick_seconds)}`"
                ),
                0x3B82F6,
            )
        )

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

    @whitelist_app.command(name="add", description="ユーザーを追加 / Add user")
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

    @whitelist_app.command(name="remove", description="ユーザーを削除 / Remove user")
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

    @whitelist_app.command(name="list", description="一覧表示 / List whitelist")
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

        ban_seconds, kick_seconds = _settings_get(
            self.settings_db,
            member.guild.id,
            self.default_ban_under_seconds,
            self.default_kick_under_seconds,
        )
        ban_delta = timedelta(seconds=ban_seconds)
        kick_delta = timedelta(seconds=kick_seconds)

        try:
            if age < ban_delta:
                reason = (
                    f"Account age {age.days}d < {_humanize_duration(ban_seconds)} "
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
                    f"Account age {age.days}d < {_humanize_duration(kick_seconds)} "
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
            await self._notify_permission_issue(member.guild, member)
        except discord.HTTPException as exc:
            await self._log(
                member.guild,
                self._embed(
                    "モデレーションエラー / Moderation Error",
                    f"{member} (ID: {member.id}) の処理に失敗しました: {exc}\nFailed to moderate {member} (ID: {member.id}): {exc}",
                    0xEF4444,
                ),
            )

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        embed = self._embed(
            "Xin chào! / Welcome!",
            (
                "Cảm ơn đã mời bot.\n"
                "Hãy dùng `setlog #kenh` để đặt kênh log.\n"
                "Vui lòng kiểm tra bot có quyền BAN/KICK và role cao hơn member cần xử lý.\n"
                "Thanks for inviting me. Use `setlog #channel` to set a log channel."
            ),
            0x3B82F6,
        )
        target = None
        if self.log_channel_id:
            target = guild.get_channel(self.log_channel_id)
        if isinstance(target, discord.TextChannel):
            await target.send(embed=embed)
        elif isinstance(guild.system_channel, discord.TextChannel):
            await guild.system_channel.send(embed=embed)
        owner = guild.owner
        if owner is None:
            try:
                owner = await guild.fetch_member(guild.owner_id)
            except (discord.Forbidden, discord.HTTPException):
                owner = None
        if owner is not None:
            try:
                await owner.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
