# MikuAutoban (dreamexploited)

English | [日本語](README.md)

![Miku](miku.jpg)

Art by [gomya0_0](https://x.com/gomya0_0)

This is Miku with a cute but serious Discord bot (discord.py) that auto-bans very new accounts and auto-kicks newer ones. It also sends a friendly embed DM before action.

## Requirements
- Python 3.13 (or 3.10+)
- Enable **Server Members Intent** in the Discord Developer Portal

## Install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration
Make a `.env` from `.env.example`:
```
DISCORD_TOKEN=your_bot_token_here
LOG_CHANNEL_ID=
BAN_UNDER_DAYS=7
KICK_UNDER_DAYS=30
```

- `LOG_CHANNEL_ID` (optional): where Miku logs actions.
- `BAN_UNDER_DAYS`: accounts younger than this get banned.
- `KICK_UNDER_DAYS`: accounts younger than this get kicked.
## Log Channel
Set the log channel in your server (requires Manage Server). Prefix or slash:
```
!setlog #channel-name
/setlog #channel-name
```
Saved to `data/log_channel.json`.

## Invite Link
```
/invite
```

## Donate Link
```
/donate
```

## Whitelist (bypass ban/kick)
Only users with ban/kick permissions can use:
```
!whitelist
!whitelist add <user_id>
!whitelist remove <user_id>
!whitelist list
/whitelist
/whitelist add user:@user
/whitelist remove user:@user
/whitelist list
```
Saved to `data/whitelist.db` (SQLite).

## Run
```bash
python main.py
```

## Permissions
The bot needs `Ban Members`, `Kick Members`, and read/send permissions in the log channel.

## have a good day!
