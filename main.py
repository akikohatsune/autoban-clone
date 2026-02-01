import os
import sys
from dotenv import load_dotenv
import discord
from discord.ext import commands


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        print(f"Missing required env var: {name}")
        sys.exit(1)
    return value


class AutoBanBot(commands.Bot):
    async def setup_hook(self) -> None:
        await self.load_extension("cogs.moderation")
        await self.load_extension("cogs.invite")
        await self.tree.sync()


def main() -> None:
    load_dotenv()

    token = _require_env("DISCORD_TOKEN")

    intents = discord.Intents.default()
    intents.members = True  # needed for on_member_join

    bot = AutoBanBot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready() -> None:
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    bot.run(token)


if __name__ == "__main__":
    main()
