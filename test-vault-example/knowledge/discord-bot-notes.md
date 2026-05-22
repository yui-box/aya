# Discord Bot — Technical Notes

#knowledge #discord #bot

## How Aya's bot works

1. Connects to Discord gateway via WebSocket (discord.py handles this)
2. Listens to all messages in channels where it has access (`on_message` event)
3. Only responds when the bot is mentioned (`client.user in message.mentions`)
4. Extracts the question, runs the RAG query, and replies

## Required intents

In Discord Developer Portal → your app → Bot:
- ✅ `MESSAGE CONTENT INTENT` — without this, `message.content` arrives empty
- ✅ `GUILD MESSAGES` — to receive server messages
- ✅ `DIRECT MESSAGES` — optional, for DMs

## Discord limits

- Messages: maximum **2,000 characters** per message
- Rate limit: ~5 messages per second per channel
- Embed: up to 6,000 characters total, but more complex to implement

## How to invite the bot to a server

1. Developer Portal → OAuth2 → URL Generator
2. Scopes: `bot`
3. Bot Permissions: `Send Messages`, `Read Message History`, `Read Messages/View Channels`
4. Copy the URL and open it in a browser (with a server admin account)

## Planned commands for Aya

| Command | Function |
|---|---|
| `@Aya [question]` | RAG over the vault |
| `!briefing` | Manual morning summary |
| `!emails` | Last 10 unread emails |
| `!draft reply to email N` | Draft reply for email N |
| `!analyze` | Multi-perspective analysis (with attachment or text) |
| `!reminders` | Reminders for the next 7 days |

## Known issues

- Mention parsing with `message.clean_content` is fragile — use `message.content` with `<@BOT_ID>` instead (AYA-4)
- `query_engine` is initialized synchronously before connecting to Discord — if Qdrant is empty, queries fail silently (AYA-2)
