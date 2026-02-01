# MikuAutoban (dreamexploited)

[English](README.en.md) | 日本語

![Miku](miku.jpg)

これは、かわいいけれど真面目なDiscordボット（discord.py）です。新しすぎるアカウントは自動BAN、少し新しいアカウントは自動KICKします。実行前にフレンドリーな埋め込みDMを送ります（DMが開放されている場合）。

## 必要条件
- Python 3.13（または 3.10+）
- Discord Developer Portal で **Server Members Intent** を有効化

## インストール
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 設定
`.env.example` から `.env` を作成:
```
DISCORD_TOKEN=your_bot_token_here
LOG_CHANNEL_ID=
BAN_UNDER_DAYS=7
KICK_UNDER_DAYS=30
```

- `LOG_CHANNEL_ID`（任意）: ログ出力先チャンネル
- `BAN_UNDER_DAYS`: この日数より新しいアカウントはBAN
- `KICK_UNDER_DAYS`: この日数より新しいアカウントはKICK

## ログチャンネル
サーバー内でログチャンネルを設定（Manage Server 権限が必要）。prefix または slash:
```
!setlog #channel-name
/setlog #channel-name
```
`data/log_channel.json` に保存されます。

![Miku](miku.jpg)

## ホワイトリスト（BAN/KICK回避）
BAN/KICK 権限を持つユーザーのみ使用可能:
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
`data/whitelist.db`（SQLite）に保存されます。

## 実行
```bash
python main.py
```

## 権限
ボットには `Ban Members`、`Kick Members`、ログチャンネルでの読み取り/送信権限が必要です。

## have a good day!
