import discord
from discord.ext import commands

DONATE_URL = ""


class Invite(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _embed(self, title: str, description: str, color: int) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=color)

    def _donate_url(self) -> str:
        return DONATE_URL.strip()

    async def _send_ctx(
        self, ctx: commands.Context, embed: discord.Embed, ephemeral: bool = False
    ) -> None:
        if ctx.interaction:
            if ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(embed=embed, ephemeral=ephemeral)
            else:
                await ctx.interaction.response.send_message(
                    embed=embed, ephemeral=ephemeral
                )
        else:
            await ctx.send(embed=embed)

    def _invite_url(self) -> str:
        app_id = self.bot.application_id
        if not app_id and self.bot.user:
            app_id = self.bot.user.id
        if not app_id:
            return ""
        perms = discord.Permissions(
            ban_members=True,
            kick_members=True,
            view_channel=True,
            send_messages=True,
        )
        return discord.utils.oauth_url(
            app_id,
            permissions=perms,
            scopes=("bot", "applications.commands"),
        )

    @commands.hybrid_command(name="invite")
    async def invite(self, ctx: commands.Context) -> None:
        url = self._invite_url()
        if not url:
            embed = self._embed(
                "招待 / Invite",
                "招待リンクを生成できませんでした。\nCould not generate invite link.",
                0xEF4444,
            )
            await self._send_ctx(ctx, embed, ephemeral=True)
            return
        embed = self._embed(
            "招待 / Invite",
            f"[ここから招待できます]({url})\nInvite link: {url}",
            0x3B82F6,
        )
        await self._send_ctx(ctx, embed, ephemeral=True)

    @commands.hybrid_command(name="donate")
    async def donate(self, ctx: commands.Context) -> None:
        url = self._donate_url()
        if not url:
            embed = self._embed(
                "寄付 / Donate",
                "寄付リンクが設定されていません。\nDonate link is not configured.",
                0xF59E0B,
            )
            await self._send_ctx(ctx, embed, ephemeral=True)
            return
        embed = self._embed(
            "寄付 / Donate",
            f"[こちらから寄付できます]({url})\nDonate link: {url}",
            0x22C55E,
        )
        await self._send_ctx(ctx, embed, ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Invite(bot))
