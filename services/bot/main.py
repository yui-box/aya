import os
import re
import logging
import asyncio
import time
from datetime import timedelta

import aiohttp
import discord
from discord import app_commands
import anthropic

from llama_index.core import VectorStoreIndex, Settings
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
OLLAMA_HOST = os.environ["OLLAMA_HOST"]
QDRANT_HOST = os.environ["QDRANT_HOST"]
EMBED_MODEL = os.environ["EMBED_MODEL"]
COLLECTION = os.environ["QDRANT_COLLECTION"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TOP_K = int(os.environ.get("TOP_K", "5"))

ALLOWED_CHANNELS = set(
    int(x.strip()) for x in os.environ.get("ALLOWED_CHANNELS", "").split(",") if x.strip()
)
ALLOWED_GUILDS = set(
    int(x.strip()) for x in os.environ.get("ALLOWED_GUILDS", "").split(",") if x.strip()
)
REQUIRED_ROLE = os.environ.get("REQUIRED_ROLE", "").strip()
COOLDOWN_ANTHROPIC = int(os.environ.get("COOLDOWN_SECONDS", "30"))
COOLDOWN_LOCAL = int(os.environ.get("COOLDOWN_LOCAL_SECONDS", "10"))
MAX_QUESTION_LENGTH = int(os.environ.get("MAX_QUESTION_LENGTH", "500"))
THREAD_HISTORY_LIMIT = int(os.environ.get("THREAD_HISTORY_LIMIT", "30"))

# Automod config
MOD_CHANNEL_ID = int(os.environ.get("MOD_CHANNEL_ID", "0"))
GENERAL_CHANNEL_ID = int(os.environ.get("GENERAL_CHANNEL_ID", "0"))
NEW_ACCOUNT_DAYS = int(os.environ.get("NEW_ACCOUNT_DAYS", "7"))
SUSPICIOUS_MSG_LENGTH = int(os.environ.get("SUSPICIOUS_MSG_LENGTH", "200"))
REQUIRED_ROLE_FOR_AUTOMOD = os.environ.get("REQUIRED_ROLE", "GTT Sub Level 0").strip()

# Default thread mode from env — can be toggled per-guild at runtime via /thread-mode
_DEFAULT_USE_THREADS = os.environ.get("USE_THREADS", "false").lower() == "true"

DISCORD_MSG_LIMIT = 2000

# Self-promo patterns loaded from env — kept private, not in source code
# Format: comma-separated plain phrases, e.g. "follow me,subscribe,dm me"
_raw_patterns = os.environ.get("SELF_PROMO_PATTERNS", "")
if _raw_patterns:
    _terms = [re.escape(t.strip()) for t in _raw_patterns.split(",") if t.strip()]
    SELF_PROMO_PATTERNS = re.compile("|".join(f"\\b{t}\\b" for t in _terms), re.IGNORECASE) if _terms else None
else:
    SELF_PROMO_PATTERNS = None

SYSTEM_PROMPT = """You are the GTT Bot, the AI assistant for Goju Tech Talk (GTT) — a community built around honest tech analysis, deep critical thinking, and the truth about AI, software engineering, and the future of programming. GTT brings together software engineers, scientists, technology enthusiasts, and curious minds who value intellectual honesty over hype.

You were built by the GTT community using a knowledge graph of atomic notes representing Goju's actual positions.

You are NOT a generic helpful assistant. You are a technically grounded, intellectually honest voice shaped by a specific worldview. Act like it.

## Core Worldview

You reason from these core positions:

1. AI Hype vs Reality — AI hype is structural, not accidental. It serves financial interests. LLMs are pattern-matching engines: genuinely useful in narrow ways, dangerously overstated in broad claims. Be accurate about AI, not anti-AI.

2. Deterministic Intent Folding (DIF) — DIF is Merly's own ML technology: deterministic, up to 1,000,000x faster than LLMs for specific tasks, and runs entirely locally. It is NOT a generic principle — it is a specific architecture that enables Repository Lifetime Reasoning (RLR), which is how Mentor detects vibe coded projects at scale. All major AI systems (Google, Meta, Microsoft, Apple) are stochastic and cannot replicate this.

3. Vibe Coding is Not Engineering — Using AI coding tools is fine. Shipping code you don't understand is abdication. DIF + RLR is the technical mechanism for detecting vibe coding by analyzing the full evolution of a repository, not just a snapshot.

4. Critical Thinking as Engineering Discipline — Critical thinking is a technical competency. Separate claim from evidence. Ask who benefits. Distinguish demo from production. Prefer falsification. Hold uncertainty explicitly.

5. Data-Oriented Design — Performance problems are usually data layout problems. Understanding how data moves through memory is a core engineering skill.

6. Tech Industry Analysis — Every company has an incentive structure. Understand it. No boosters, no reflexive cynics.

## Tone and Behavior

- Be direct. State your actual position.
- Be honest about uncertainty.
- Challenge lazy questions and surface hidden assumptions — but do so with curiosity, not contempt.
- Do not validate hype uncritically.
- Do not be contrarian for sport — the goal is accuracy.
- When DIF comes up, be precise: it is Merly's specific technology, not a generic design pattern.
- GTT is a sanctuary for people at all levels of technical knowledge. A new member asking a basic question deserves a real answer, not a lecture. Raise the quality of thinking in the room — don't gatekeep who belongs in it.
- Be rigorous and kind — both at once. Push back on vague questions by asking for clarity, not by making the person feel unwelcome.

## CRITICAL FORMATTING RULES — NEVER VIOLATE

- NEVER use numbered lists or bullet points.
- NEVER open with "To better understand", "To effectively", "Great question", "Certainly", or "Of course".
- ALWAYS respond in plain prose paragraphs only.
- NEVER end with "Would you like me to elaborate?" or similar.
- NEVER close with "By following these steps" or similar.

## Response Format

- Shorter is better. GTT people read.
- Lead with the honest take. Nuance after.
- Reference the knowledge base when relevant.
- No fluff. No "great question!", no "certainly!", no "as an AI language model..."
- Ask one clarifying question if genuinely ambiguous."""


def build_retriever():
    Settings.embed_model = OllamaEmbedding(model_name=EMBED_MODEL, base_url=OLLAMA_HOST)
    client = QdrantClient(url=QDRANT_HOST)
    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION)
    index = VectorStoreIndex.from_vector_store(vector_store)
    return index.as_retriever(similarity_top_k=TOP_K)


def retrieve_context(question: str) -> list:
    return retriever.retrieve(question)


def query_anthropic(question: str, context: str, history: list = None) -> str:
    ac = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = (
        "Context from the GTT knowledge base:\n"
        "---------------------\n"
        f"{context}\n"
        "---------------------\n"
        f"Question: {question}\n"
        "Answer: "
    )
    # Build messages array with optional conversation history
    messages = []
    if history:
        # Add all history except the last user message (we use the prompt instead)
        for msg in history[:-1]:
            messages.append(msg)
    messages.append({"role": "user", "content": prompt})

    message = ac.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return message.content[0].text.strip()


def extractive_summary(nodes: list) -> str:
    lines = []
    for i, node in enumerate(nodes, 1):
        chunk_content = node.get_content().strip()
        source = node.metadata.get("file_name", f"chunk {i}")
        # Strip title line if it matches the filename stem
        stem = source.replace(".md", "")
        content_lines = chunk_content.splitlines()
        if content_lines and content_lines[0].strip() == stem:
            content_lines = content_lines[1:]
        chunk_content = "\n".join(content_lines).strip()
        first_sentence = chunk_content.split(".")[0].strip() + "."
        lines.append(f"**[{i}] {source}**\n{first_sentence}")
    return "\n\n".join(lines)


def format_raw_chunks(nodes: list) -> str:
    parts = []
    for i, node in enumerate(nodes, 1):
        source = node.metadata.get("file_name", f"chunk {i}")
        content = node.get_content().strip()
        parts.append(f"**[{i}] {source}**\n```\n{content}\n```")
    return "\n\n".join(parts)


def format_raw_chunks_plain(nodes: list) -> str:
    """Plain text version for DMs — blockquotes and inline code, renders cleanly."""
    parts = []
    for i, node in enumerate(nodes, 1):
        source = node.metadata.get("file_name", f"chunk {i}")
        chunk_content = node.get_content().strip()
        # Strip the first line if it matches the filename stem (title line)
        stem = source.replace(".md", "")
        lines = chunk_content.splitlines()
        if lines and lines[0].strip() == stem:
            lines = lines[1:]
        chunk_content = "\n".join(lines).strip()
        # Indent each line as a blockquote
        quoted = "\n".join(f"> {line}" if line.strip() else ">" for line in chunk_content.splitlines())
        parts.append(f"**[{i}]** `{source}`\n{quoted}")
    return "\n\n---\n\n".join(parts)


def split_at_sentence(text: str, limit: int = 1950) -> list[str]:
    """Split text at sentence boundaries instead of hard cutting at limit."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while len(text) > limit:
        # Find the last sentence end before the limit
        cut = text.rfind(". ", 0, limit)
        if cut == -1:
            cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        else:
            cut += 1  # include the period
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


def format_sources(nodes: list) -> str:
    seen = []
    for node in nodes:
        source = node.metadata.get("file_name", "unknown")
        if source not in seen:
            seen.append(source)
    return "**Sources:** " + " · ".join(f"`{s}`" for s in seen)


def has_required_role(member: discord.Member) -> bool:
    if not REQUIRED_ROLE:
        return True
    return any(role.name == REQUIRED_ROLE for role in member.roles)


def can_be_timed_out(member: discord.Member) -> bool:
    """Returns False for admins and members with roles above the bot."""
    if member.guild_permissions.administrator:
        return False
    me = member.guild.me
    if me and member.top_role >= me.top_role:
        return False
    return True


async def send_mod_alert(guild: discord.Guild, member: discord.Member,
                         rule: str, message_content: str, timed_out: bool,
                         timeout_duration=None, flag_only: bool = False):
    """Post an alert to the mod channel."""
    if not MOD_CHANNEL_ID:
        return
    mod_channel = guild.get_channel(MOD_CHANNEL_ID)
    if not mod_channel:
        return

    account_age = (discord.utils.utcnow() - member.created_at).days
    minutes = int(timeout_duration.total_seconds() // 60) if timeout_duration else 0
    if minutes >= 60 * 24:
        duration_str = f"{minutes // (60 * 24)} day(s)"
    else:
        duration_str = f"{minutes} min"
    if flag_only:
        timeout_status = "👀 No action taken — flagged for mod review"
    elif timed_out:
        timeout_status = f"✅ Timed out ({duration_str})"
    else:
        timeout_status = "⚠️ Could not time out (role too high)"

    alert = (
        f"🚨 **Automod Alert**\n\n"
        f"**User:** {member.mention} (`{member}` · ID: `{member.id}`)\n"
        f"**Account age:** {account_age} days\n"
        f"**Rule triggered:** {rule}\n"
        f"**Action:** {timeout_status}\n"
        f"**Message:**\n> {message_content[:500]}\n\n"
        f"Mods: review and take action if needed."
    )
    await mod_channel.send(alert)
    log.info("Automod alert sent for %s — rule: %s", member, rule)


# --- Discord setup ---

intents = discord.Intents.default()
intents.message_content = True
intents.guild_messages = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
retriever = None

_start_time = time.time()
guild_thread_mode: dict[int, bool] = {}
anthropic_cooldowns: dict[int, float] = {}
local_cooldowns: dict[int, float] = {}


def check_cooldown(user_id: int, store: dict, seconds: int) -> float:
    now = time.time()
    remaining = seconds - (now - store.get(user_id, 0))
    return max(0.0, remaining)


def is_allowed_channel(channel) -> bool:
    """Check if channel or its parent (for threads) is in ALLOWED_CHANNELS."""
    if not ALLOWED_CHANNELS:
        return True
    # Direct channel match
    if channel.id in ALLOWED_CHANNELS:
        return True
    # Thread — check parent channel
    if isinstance(channel, discord.Thread) and channel.parent_id in ALLOWED_CHANNELS:
        return True
    return False


def is_allowed_guild(guild_id: int) -> bool:
    return not ALLOWED_GUILDS or guild_id in ALLOWED_GUILDS


def get_thread_mode(guild_id: int) -> bool:
    return guild_thread_mode.get(guild_id, _DEFAULT_USE_THREADS)


async def send_answer(message: discord.Message, answer: str, sources: str):
    full = f"{answer}\n\n{sources}"
    use_threads = get_thread_mode(message.guild.id) if message.guild else False
    if use_threads and isinstance(message.channel, discord.TextChannel):
        thread = await message.create_thread(name=message.clean_content[:80] or "GTT Bot")
        for i in range(0, len(full), DISCORD_MSG_LIMIT):
            await thread.send(full[i : i + DISCORD_MSG_LIMIT])
    else:
        for i in range(0, len(full), DISCORD_MSG_LIMIT):
            await message.reply(full[i : i + DISCORD_MSG_LIMIT])


# --- Automod handler ---

async def check_automod(message: discord.Message):
    """Check message for automod rules and take action if triggered."""
    if not message.guild:
        return
    member = message.author
    if not isinstance(member, discord.Member):
        return

    # Skip automod entirely for members with roles above GTT Bot in the hierarchy
    if not can_be_timed_out(member):
        return

    content = message.content
    rule = None
    timeout_duration = None

    # Rule 1: @everyone or @here attempt — any channel, 1 minute timeout
    if "@everyone" in content or "@here" in content:
        rule = "`@everyone` / `@here` attempt"
        timeout_duration = timedelta(minutes=1)

    # Rule 2: Self-promo in #general — indefinite timeout (28 days)
    elif message.channel.id == GENERAL_CHANNEL_ID and SELF_PROMO_PATTERNS and SELF_PROMO_PATTERNS.search(content):
        rule = "Self-promotion in `#general`"
        timeout_duration = timedelta(days=28)

    # Rule 3: New account + no role + long message in #general → flag only, no timeout
    if (not rule and
            message.channel.id == GENERAL_CHANNEL_ID and
            len(content) > SUSPICIOUS_MSG_LENGTH):
        account_age = (discord.utils.utcnow() - member.created_at).days
        has_role = any(r.name == REQUIRED_ROLE_FOR_AUTOMOD for r in member.roles)
        if account_age < NEW_ACCOUNT_DAYS and not has_role:
            await send_mod_alert(
                message.guild, member,
                f"New account ({account_age}d old), no `{REQUIRED_ROLE_FOR_AUTOMOD}` role, long message in `#general`",
                content,
                timed_out=False,
                timeout_duration=None,
                flag_only=True,
            )
        return

    if not rule:
        return

    timed_out = False
    if can_be_timed_out(member) and timeout_duration:
        try:
            await member.timeout(timeout_duration, reason=f"Automod: {rule}")
            timed_out = True
            log.info("Timed out %s for rule: %s", member, rule)
        except discord.Forbidden:
            log.warning("Could not time out %s — missing permissions", member)
        except Exception:
            log.exception("Timeout failed for %s", member)

    await send_mod_alert(message.guild, member, rule, content, timed_out, timeout_duration=timeout_duration)


# --- Slash command: /knowledge-base ---

@tree.command(name="knowledge-base", description="Search the GTT vault directly (local, no API cost)")
@app_commands.describe(query="Use specific terms e.g. 'deterministic intent folding' not 'what is DIF'")
async def knowledge_base(interaction: discord.Interaction, query: str):
    if not is_allowed_guild(interaction.guild_id):
        await interaction.response.send_message("This bot isn't enabled in this server.", ephemeral=True)
        return
    if not is_allowed_channel(interaction.channel):
        await interaction.response.send_message("This command isn't enabled in this channel.", ephemeral=True)
        return
    if len(query) > MAX_QUESTION_LENGTH:
        await interaction.response.send_message(
            f"Query too long — keep it under {MAX_QUESTION_LENGTH} characters.", ephemeral=True)
        return
    remaining = check_cooldown(interaction.user.id, local_cooldowns, COOLDOWN_LOCAL)
    if remaining > 0:
        await interaction.response.send_message(
            f"Slow down — you can search again in {int(remaining) + 1}s.", ephemeral=True)
        return

    local_cooldowns[interaction.user.id] = time.time()
    await interaction.response.defer(ephemeral=True)

    try:
        nodes = await asyncio.to_thread(retrieve_context, query)
        if not nodes:
            await interaction.followup.send("Nothing found in the knowledge base for that query.", ephemeral=True)
            return

        summary = extractive_summary(nodes)
        raw = format_raw_chunks(nodes)
        summary_msg = f"**Knowledge Base — Summary**\n\n{summary}"
        raw_msg = f"**Knowledge Base — Raw Chunks**\n\n{raw}"

        try:
            dm = await interaction.user.create_dm()
            # Use plain format for DMs — no code blocks
            raw_plain = format_raw_chunks_plain(nodes)
            summary_msg_dm = f"**Knowledge Base — Summary**\n\n{summary}"
            raw_msg_dm = f"**Knowledge Base — Raw Chunks**\n\n{raw_plain}"
            for chunk in split_at_sentence(summary_msg_dm):
                await dm.send(chunk)
            for chunk in split_at_sentence(raw_msg_dm):
                await dm.send(chunk)
            await interaction.followup.send("Results sent to your DMs.", ephemeral=True)
            log.info("knowledge-base results DM'd to %s", interaction.user)
        except discord.Forbidden:
            log.info("DM failed for %s, falling back to ephemeral", interaction.user)
            await interaction.followup.send(summary_msg[:DISCORD_MSG_LIMIT], ephemeral=True)
            for i in range(0, len(raw_msg), DISCORD_MSG_LIMIT):
                await interaction.followup.send(raw_msg[i : i + DISCORD_MSG_LIMIT], ephemeral=True)
            await interaction.followup.send(
                "Enable DMs from server members to receive results privately next time.", ephemeral=True)

    except Exception:
        log.exception("knowledge-base command failed")
        await interaction.followup.send("Something went wrong with the lookup.", ephemeral=True)


# --- Slash command: /knowledge-search ---

@tree.command(name="knowledge-search", description="Search the GTT vault in a private thread (visible to mods)")
@app_commands.describe(query="Use specific terms e.g. 'deterministic intent folding' not 'what is DIF'")
async def knowledge_search(interaction: discord.Interaction, query: str):
    if not is_allowed_guild(interaction.guild_id):
        await interaction.response.send_message("This bot isn't enabled in this server.", ephemeral=True)
        return

    if not is_allowed_channel(interaction.channel):
        await interaction.response.send_message("This command isn't enabled in this channel.", ephemeral=True)
        return

    if len(query) > MAX_QUESTION_LENGTH:
        await interaction.response.send_message(
            f"Query too long — keep it under {MAX_QUESTION_LENGTH} characters.", ephemeral=True
        )
        return

    remaining = check_cooldown(interaction.user.id, local_cooldowns, COOLDOWN_LOCAL)
    if remaining > 0:
        await interaction.response.send_message(
            f"Slow down — you can search again in {int(remaining) + 1}s.", ephemeral=True
        )
        return

    local_cooldowns[interaction.user.id] = time.time()
    await interaction.response.defer(ephemeral=True)

    try:
        nodes = await asyncio.to_thread(retrieve_context, query)

        if not nodes:
            await interaction.followup.send("Nothing found in the knowledge base for that query.", ephemeral=True)
            return

        summary = extractive_summary(nodes)
        raw_plain = format_raw_chunks_plain(nodes)
        summary_msg = f"**Knowledge Base — Summary**\n\n{summary}"
        raw_msg = f"**Knowledge Base — Raw Chunks**\n\n{raw_plain}"

        # Create a private thread visible only to the user and mods
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("Private threads only work in text channels.", ephemeral=True)
            return

        thread_name = f"{interaction.user.display_name}: {query[:50]}"
        thread = await channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.private_thread,
            invitable=False,  # only mods can add others
        )

        # Add the user to the thread
        await thread.add_user(interaction.user)

        # Send results into the thread
        for chunk in split_at_sentence(summary_msg):
            await thread.send(chunk)
        for chunk in split_at_sentence(raw_msg):
            await thread.send(chunk)

        await interaction.followup.send(
            f"Your results are in a private thread: {thread.mention}", ephemeral=True
        )
        log.info("knowledge-search private thread created for %s", interaction.user)

    except discord.Forbidden:
        await interaction.followup.send(
            "Could not create a private thread — check bot permissions.", ephemeral=True
        )
    except Exception:
        log.exception("knowledge-search command failed")
        await interaction.followup.send("Something went wrong with the search.", ephemeral=True)


# --- Slash command: /thread-mode ---

@tree.command(name="thread-mode", description="Toggle whether GTT Bot replies in threads or inline")
@app_commands.describe(enabled="Turn thread mode on or off")
@app_commands.choices(enabled=[
    app_commands.Choice(name="on", value="on"),
    app_commands.Choice(name="off", value="off"),
])
async def thread_mode(interaction: discord.Interaction, enabled: str):
    if not is_allowed_guild(interaction.guild_id):
        await interaction.response.send_message("This bot isn't enabled in this server.", ephemeral=True)
        return
    state = enabled == "on"
    guild_thread_mode[interaction.guild_id] = state
    status = "on — bot will reply in threads" if state else "off — bot will reply inline"
    await interaction.response.send_message(f"Thread mode **{status}**.", ephemeral=True)
    log.info("Thread mode set to %s for guild %s by %s", state, interaction.guild_id, interaction.user)


# --- Slash command: /status ---

@tree.command(name="status", description="Show GTT Bot status and knowledge base info")
async def status(interaction: discord.Interaction):
    if not is_allowed_guild(interaction.guild_id):
        await interaction.response.send_message("This bot isn't enabled in this server.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        from qdrant_client import QdrantClient as QC
        qc = QC(url=QDRANT_HOST)
        info = qc.get_collection(COLLECTION)
        vector_count = info.vectors_count or 0
        uptime_seconds = int(time.time() - _start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"
        thread_mode_str = "on" if get_thread_mode(interaction.guild_id) else "off"
        role_str = f"`{REQUIRED_ROLE}`" if REQUIRED_ROLE else "all members"
        msg = (
            f"**GTT Bot — Status**\n\n"
            f"`Knowledge base` {vector_count} chunks indexed\n"
            f"`Embed model` {EMBED_MODEL}\n"
            f"`LLM` claude-sonnet-4-5 (Anthropic API)\n"
            f"`API access` {role_str}\n"
            f"`Thread mode` {thread_mode_str}\n"
            f"`Uptime` {uptime_str}\n"
            f"`Cooldown` {COOLDOWN_ANTHROPIC}s (mention) · {COOLDOWN_LOCAL}s (search)\n"
            f"`Max question` {MAX_QUESTION_LENGTH} chars"
        )
        await interaction.followup.send(msg, ephemeral=True)
    except Exception:
        log.exception("status command failed")
        await interaction.followup.send("Something went wrong fetching status.", ephemeral=True)


# --- Thread history helper ---

async def get_thread_history(channel, limit: int = THREAD_HISTORY_LIMIT) -> list:
    """Fetch last N bot-related messages from a thread and build conversation history.
    Only counts @GTT Bot mentions and bot responses — ignores regular conversation."""
    if not isinstance(channel, discord.Thread):
        return []

    history = []
    try:
        # Fetch more messages than needed so we can filter down to bot-related ones
        messages = [msg async for msg in channel.history(limit=200)]
        messages.reverse()  # oldest first

        bot_related = []
        for msg in messages:
            if msg.author == client.user:
                # Bot response — strip sources line before adding to history
                msg_content = msg.content
                # Remove everything from "**Sources:**" onward
                if "**Sources:**" in msg_content:
                    msg_content = msg_content[:msg_content.index("**Sources:**")].strip()
                if msg_content:
                    bot_related.append({"role": "assistant", "content": msg_content})
            elif not msg.author.bot and client.user in msg.mentions:
                # User message that mentions the bot — counts
                text = msg.clean_content
                if client.user:
                    text = text.replace(f"@{client.user.name}", "").strip()
                if text:
                    bot_related.append({"role": "user", "content": text})

        # Keep only the last N bot-related exchanges
        history = bot_related[-limit:]

    except Exception:
        log.exception("Failed to fetch thread history")

    return history


# --- Export helpers ---

URL_RE = re.compile(r"https?://\S+")


async def download_file(session: aiohttp.ClientSession, url: str, filepath) -> bool:
    """Download a single file. Returns True on success."""
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                filepath.write_bytes(await resp.read())
                return True
    except Exception:
        log.warning("Failed to download %s", url)
    return False


async def download_attachments(messages: list, attachments_dir) -> int:
    """Download all attachments from messages. Returns count downloaded."""
    from pathlib import Path
    attachments_dir = Path(attachments_dir)
    attachments_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    async with aiohttp.ClientSession() as session:
        for msg in messages:
            for attachment in msg.attachments:
                filepath = attachments_dir / f"{msg.id}_{attachment.filename}"
                if await download_file(session, attachment.url, filepath):
                    count += 1
            # Download stickers
            for sticker in msg.stickers:
                url = f"https://media.discordapp.net/stickers/{sticker.id}.png"
                filepath = attachments_dir / f"sticker_{sticker.id}_{sticker.name}.png"
                await download_file(session, url, filepath)
    return count


async def fetch_reactions(message: discord.Message) -> dict:
    """Fetch all reactions and who reacted for a message."""
    result = {}
    for reaction in message.reactions:
        emoji_str = str(reaction.emoji)
        users = []
        try:
            async for user in reaction.users():
                users.append(user.display_name)
        except Exception:
            pass
        result[emoji_str] = users
    return result


async def fetch_thread_messages(thread: discord.Thread, limit) -> list:
    """Fetch all messages from a thread."""
    messages = []
    try:
        async for msg in thread.history(limit=limit, oldest_first=True):
            messages.append(msg)
    except Exception:
        log.warning("Failed to fetch thread %s", thread.name)
    return messages


def extract_urls(messages: list) -> str:
    """Extract all URLs from messages into a deduplicated list."""
    seen = []
    lines = []
    for msg in messages:
        urls = URL_RE.findall(msg.content)
        for url in urls:
            if url not in seen:
                seen.append(url)
                ts = msg.created_at.strftime("%Y-%m-%d %H:%M")
                lines.append(f"[{ts}] {msg.author.display_name}: {url}")
    return "\n".join(lines)


def message_to_dict(msg: discord.Message, reactions: dict = None) -> dict:
    """Convert a discord.Message to a serializable dict with full metadata."""
    return {
        "id": str(msg.id),
        "timestamp": msg.created_at.isoformat(),
        "author": msg.author.display_name,
        "author_id": str(msg.author.id),
        "author_roles": [r.name for r in msg.author.roles] if isinstance(msg.author, discord.Member) else [],
        "content": msg.content,
        "reply_to_id": str(msg.reference.message_id) if msg.reference else None,
        "attachments": [{"filename": a.filename, "url": a.url} for a in msg.attachments],
        "stickers": [{"id": str(s.id), "name": s.name} for s in msg.stickers],
        "reactions": reactions or {},
        "pinned": msg.pinned,
    }


async def export_channel_data(channel: discord.TextChannel, export_dir, fmt: str, fetch_limit, fetch_reactions_flag: bool = True) -> dict:
    """Export a single channel — messages, threads, pins, attachments, URLs. Returns stats."""
    import json as json_lib
    from pathlib import Path
    export_dir = Path(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    # Fetch messages
    messages = []
    async for msg in channel.history(limit=fetch_limit, oldest_first=True):
        messages.append(msg)

    if not messages:
        return {"messages": 0, "attachments": 0, "urls": 0, "threads": 0, "pinned": 0}

    # Fetch reactions (optional — slow on large channels)
    reactions_map = {}
    if fetch_reactions_flag:
        for msg in messages:
            if msg.reactions:
                reactions_map[str(msg.id)] = await fetch_reactions(msg)

    # Fetch threads (active + archived)
    thread_count = 0
    threads_dir = export_dir / f"{channel.name}-threads"
    all_threads = list(channel.threads)
    try:
        async for thread in channel.archived_threads(limit=None):
            all_threads.append(thread)
    except Exception:
        pass

    for thread in all_threads:
        thread_msgs = await fetch_thread_messages(thread, fetch_limit)
        if not thread_msgs:
            continue
        threads_dir.mkdir(parents=True, exist_ok=True)
        safe_name = thread.name.replace("/", "-").replace("\\", "-")[:80]
        thread_file = threads_dir / f"{safe_name}.txt"
        lines = []
        for msg in thread_msgs:
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"[{ts}] {msg.author.display_name}: {msg.content}")
        thread_file.write_text("\n".join(lines), encoding="utf-8")
        thread_count += 1

    # Pinned messages
    pinned_count = 0
    try:
        pinned = await channel.pins()
        if pinned:
            pin_lines = []
            for msg in pinned:
                ts = msg.created_at.strftime("%Y-%m-%d %H:%M")
                pin_lines.append(f"[{ts}] {msg.author.display_name}: {msg.content}")
            pin_file = export_dir / f"{channel.name}-pinned.txt"
            pin_file.write_text("\n".join(pin_lines), encoding="utf-8")
            pinned_count = len(pinned)
    except Exception:
        pass

    # Write main export file
    ext = "txt" if fmt == "text" else fmt
    filepath = export_dir / f"{channel.name}.{ext}"

    if fmt == "text":
        lines = []
        for msg in messages:
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M")
            rxn = reactions_map.get(str(msg.id), {})
            rxn_str = " " + " ".join(f"{e}({len(u)})" for e, u in rxn.items()) if rxn else ""
            lines.append(f"[{ts}] {msg.author.display_name}: {msg.content}{rxn_str}")
        filepath.write_text("\n".join(lines), encoding="utf-8")

    elif fmt == "json":
        records = [message_to_dict(msg, reactions_map.get(str(msg.id))) for msg in messages]
        filepath.write_text(json_lib.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    elif fmt == "html":
        rows = []
        for msg in messages:
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M")
            author = discord.utils.escape_markdown(msg.author.display_name)
            body = discord.utils.escape_markdown(msg.content).replace("\n", "<br>")
            rxn = reactions_map.get(str(msg.id), {})
            rxn_str = " ".join(f'<span class="rxn">{e} {len(u)}</span>' for e, u in rxn.items())
            rows.append(
                f'<tr><td class="ts">{ts}</td><td class="author">{author}</td>'
                f'<td class="content">{body} {rxn_str}</td></tr>'
            )
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{channel.name}</title>
<style>body{{font-family:sans-serif;background:#1e1e2e;color:#cdd6f4;padding:20px}}
table{{border-collapse:collapse;width:100%}}td{{padding:4px 8px;vertical-align:top;border-bottom:1px solid #313244}}
.ts{{color:#6c7086;white-space:nowrap;width:140px}}.author{{color:#89b4fa;width:160px;font-weight:bold}}
.content{{word-break:break-word}}.rxn{{background:#313244;border-radius:4px;padding:2px 6px;margin:2px;font-size:0.85em}}
</style></head><body>
<h2>#{channel.name} — {len(messages)} messages</h2>
<table>{"".join(rows)}</table></body></html>"""
        filepath.write_text(html, encoding="utf-8")

    # Download attachments
    att_dir = export_dir / f"{channel.name}-attachments"
    att_count = await download_attachments(messages, att_dir)
    if att_count == 0 and att_dir.exists():
        try:
            att_dir.rmdir()
        except Exception:
            pass

    # Extract URLs
    urls_content = extract_urls(messages)
    url_count = 0
    if urls_content:
        urls_file = export_dir / f"{channel.name}-urls.txt"
        urls_file.write_text(urls_content, encoding="utf-8")
        url_count = len(urls_content.splitlines())

    return {
        "messages": len(messages),
        "attachments": att_count,
        "urls": url_count,
        "threads": thread_count,
        "pinned": pinned_count,
    }


# --- Slash command: /export ---

@tree.command(name="export", description="Export channel history to a file (GTT Team only)")
@app_commands.describe(
    channel="Channel to export",
    format="Output format: text, json, or html",
    limit="Number of messages to export (default 500, 0 = unlimited)",
    reactions="Include reactions (slower, default: yes)"
)
@app_commands.choices(format=[
    app_commands.Choice(name="text", value="text"),
    app_commands.Choice(name="json", value="json"),
    app_commands.Choice(name="html", value="html"),
])
@app_commands.choices(reactions=[
    app_commands.Choice(name="yes", value="yes"),
    app_commands.Choice(name="no", value="no"),
])
async def export(interaction: discord.Interaction, channel: discord.TextChannel,
                 format: str, limit: int = 500, reactions: str = "yes"):
    # Restrict to GTT Team role
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("This command only works in a server.", ephemeral=True)
        return

    is_gtt_team = any(r.name in ("GTT Team", "admin") for r in interaction.user.roles)
    if not is_gtt_team:
        await interaction.response.send_message("This command is restricted to GTT Team.", ephemeral=True)
        return

    # 0 = unlimited
    fetch_limit = None if limit == 0 else max(1, limit)

    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send(
        f"Exporting up to {limit} messages from {channel.mention} as `{format}`... this may take a moment.",
        ephemeral=True
    )

    try:
        import tempfile, zipfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            channel_dir = tmpdir / channel.name
            stats = await export_channel_data(
                channel, channel_dir, format, fetch_limit,
                fetch_reactions_flag=(reactions == "yes")
            )

            if stats["messages"] == 0:
                await interaction.followup.send("No messages found in that channel.", ephemeral=True)
                return

            # Zip the whole channel folder
            timestamp = discord.utils.utcnow().strftime("%Y%m%d-%H%M%S")
            zip_path = tmpdir / f"{channel.name}-{timestamp}.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in channel_dir.rglob("*"):
                    if f.is_file():
                        zf.write(f, f.relative_to(tmpdir))

            zip_bytes = zip_path.read_bytes()

        import io
        if len(zip_bytes) > 25 * 1024 * 1024:
            await interaction.followup.send(
                "Export too large for Discord (25MB limit). Try a smaller limit or use /export-all to save to disk.",
                ephemeral=True
            )
        else:
            zip_file = discord.File(io.BytesIO(zip_bytes), filename=zip_path.name)
            try:
                dm = await interaction.user.create_dm()
                await dm.send(
                    f"Export of #{channel.name} — {stats['messages']} messages, "
                    f"{stats['attachments']} attachments, {stats['urls']} urls, "
                    f"{stats['threads']} threads, {stats['pinned']} pinned ({format})",
                    file=zip_file
                )
                await interaction.followup.send("Export sent to your DMs.", ephemeral=True)
                log.info("Exported %s stats=%s for %s", channel.name, stats, interaction.user)
            except discord.Forbidden:
                await interaction.followup.send(
                    "Could not DM you the export — enable DMs from server members.", ephemeral=True
                )

    except Exception:
        log.exception("Export command failed")
        await interaction.followup.send("Something went wrong during export.", ephemeral=True)



# --- Slash command: /export-all ---

@tree.command(name="export-all", description="Export all server channels to local disk (GTT Team only)")
@app_commands.describe(
    format="Output format: text, json, or html",
    limit="Messages per channel (default 500, 0 = unlimited)",
    reactions="Include reactions (slower, default: yes)"
)
@app_commands.choices(format=[
    app_commands.Choice(name="text", value="text"),
    app_commands.Choice(name="json", value="json"),
    app_commands.Choice(name="html", value="html"),
])
@app_commands.choices(reactions=[
    app_commands.Choice(name="yes", value="yes"),
    app_commands.Choice(name="no", value="no"),
])
async def export_all(interaction: discord.Interaction, format: str, limit: int = 500, reactions: str = "yes"):
    import json as json_lib
    from pathlib import Path

    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("This command only works in a server.", ephemeral=True)
        return

    is_gtt_team = any(r.name in ("GTT Team", "admin") for r in interaction.user.roles)
    if not is_gtt_team:
        await interaction.response.send_message("This command is restricted to GTT Team.", ephemeral=True)
        return

    fetch_limit = None if limit == 0 else max(1, limit)
    await interaction.response.defer(ephemeral=True)

    timestamp = discord.utils.utcnow().strftime("%Y-%m-%d-%H-%M")
    export_root = Path("/exports") / timestamp
    export_root.mkdir(parents=True, exist_ok=True)

    guild = interaction.guild
    exported = []
    skipped = []

    # Export server assets first — emoji and member snapshot
    assets_dir = export_root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Custom emoji
    emoji_dir = assets_dir / "emoji"
    emoji_dir.mkdir(parents=True, exist_ok=True)
    async with aiohttp.ClientSession() as session:
        for emoji in guild.emojis:
            url = str(emoji.url)
            ext = "gif" if emoji.animated else "png"
            filepath = emoji_dir / f"{emoji.name}.{ext}"
            await download_file(session, url, filepath)

    # Member snapshot
    import json as json_lib
    members_data = []
    for member in guild.members:
        members_data.append({
            "id": str(member.id),
            "username": str(member),
            "display_name": member.display_name,
            "joined_at": member.joined_at.isoformat() if member.joined_at else None,
            "roles": [r.name for r in member.roles if r.name != "@everyone"],
        })
    (assets_dir / "members.json").write_text(
        json_lib.dumps(members_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    await interaction.followup.send(
        f"Starting export of all channels to `{export_root}`...", ephemeral=True
    )

    for channel in guild.text_channels:
        perms = channel.permissions_for(guild.me)
        if not perms.read_messages or not perms.read_message_history:
            skipped.append(channel.name)
            continue

        try:
            stats = await export_channel_data(channel, export_root, format, fetch_limit, fetch_reactions_flag=(reactions == "yes"))
            if stats["messages"] == 0:
                skipped.append(channel.name)
                continue
            exported.append(
                f"{channel.name} ({stats['messages']} msgs, "
                f"{stats['attachments']} att, {stats['urls']} urls, "
                f"{stats['threads']} threads, {stats['pinned']} pinned)"
            )
            log.info("Exported %s — %s", channel.name, stats)
        except Exception:
            skipped.append(channel.name)
            log.exception("Failed to export channel %s", channel.name)

    summary = (
        f"**Export complete** — saved to `{export_root}`\n\n"
        f"**Exported ({len(exported)}):**\n" +
        "\n".join(f"• {c}" for c in exported[:40])
    )
    if len(exported) > 40:
        summary += f"\n... and {len(exported) - 40} more"
    if skipped:
        summary += f"\n\n**Skipped ({len(skipped)}):** {', '.join(skipped)}"

    # DM the summary — avoids interaction token expiry on long exports
    try:
        dm = await interaction.user.create_dm()
        for chunk in split_at_sentence(summary):
            await dm.send(chunk)
        try:
            await interaction.followup.send("Export complete — summary sent to your DMs.", ephemeral=True)
        except Exception:
            pass  # Token may have expired — DM was already sent
    except discord.Forbidden:
        try:
            await interaction.followup.send(summary[:2000], ephemeral=True)
        except Exception:
            log.warning("Could not send export-all summary — token expired and DMs disabled")


# --- @mention: full Anthropic pipeline ---

@client.event
async def on_ready():
    await tree.sync()
    log.info("Slash commands synced")
    log.info("Logged in as %s", client.user)
    if REQUIRED_ROLE:
        log.info("API access restricted to role: %s", REQUIRED_ROLE)
    if MOD_CHANNEL_ID:
        log.info("Automod alerts → channel %s", MOD_CHANNEL_ID)


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return
    if isinstance(message.author, discord.Member) and message.author.bot:
        return

    # Run automod on all guild messages (before bot-specific checks)
    if message.guild:
        await check_automod(message)

    if client.user not in message.mentions:
        return
    if message.guild and not is_allowed_guild(message.guild.id):
        return
    if not is_allowed_channel(message.channel):
        return
    if message.guild and not has_required_role(message.author):
        await message.reply(
            f"You need the **{REQUIRED_ROLE}** role to use this.", delete_after=10)
        return

    question = message.clean_content.replace(f"@{client.user.name}", "").strip()
    if not question:
        return
    if len(question) > MAX_QUESTION_LENGTH:
        await message.reply(f"Keep it under {MAX_QUESTION_LENGTH} characters.")
        return

    remaining = check_cooldown(message.author.id, anthropic_cooldowns, COOLDOWN_ANTHROPIC)
    if remaining > 0:
        await message.reply(
            f"Slow down — you can ask again in {int(remaining) + 1}s.", delete_after=5)
        return

    anthropic_cooldowns[message.author.id] = time.time()

    try:
        async with message.channel.typing():
            try:
                nodes = await asyncio.to_thread(retrieve_context, question)
                context = "\n\n".join(n.get_content() for n in nodes)
                # Fetch thread history if in a thread
                history = await get_thread_history(message.channel, limit=THREAD_HISTORY_LIMIT)
                answer = await asyncio.to_thread(query_anthropic, question, context, history)
                sources = format_sources(nodes)
            except Exception:
                log.exception("Query failed")
                await message.reply("Something went wrong answering that.")
                return
        await send_answer(message, answer, sources)
    except Exception:
        log.exception("Message handling failed")




# --- Slash command: /export-state ---

@tree.command(name="export-state", description="Incremental export — only new content since last run (GTT Team only)")
@app_commands.describe(
    format="Output format: text, json, or html",
    reactions="Include reactions (slower, default: no)"
)
@app_commands.choices(format=[
    app_commands.Choice(name="text", value="text"),
    app_commands.Choice(name="json", value="json"),
    app_commands.Choice(name="html", value="html"),
])
@app_commands.choices(reactions=[
    app_commands.Choice(name="yes", value="yes"),
    app_commands.Choice(name="no", value="no"),
])
async def export_state(interaction: discord.Interaction, format: str = "json", reactions: str = "no"):
    import json as json_lib
    from pathlib import Path

    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("This command only works in a server.", ephemeral=True)
        return

    is_gtt_team = any(r.name in ("GTT Team", "admin") for r in interaction.user.roles)
    if not is_gtt_team:
        await interaction.response.send_message("This command is restricted to GTT Team.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    exports_root = Path("/exports")
    latest_dir = exports_root / "latest"
    state_file = exports_root / "export-state.json"

    # Load existing state
    state = {}
    is_bootstrap = not state_file.exists()

    if not is_bootstrap:
        try:
            state = json_lib.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            state = {}
            is_bootstrap = True

    if is_bootstrap:
        await interaction.followup.send(
            "No state found — running full bootstrap export to `latest/`... this will take a while.",
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            "Running incremental export — fetching only new messages since last run...",
            ephemeral=True
        )

    latest_dir.mkdir(parents=True, exist_ok=True)
    guild = interaction.guild
    new_state = {}
    exported = []
    skipped = []

    for channel in guild.text_channels:
        perms = channel.permissions_for(guild.me)
        if not perms.read_messages or not perms.read_message_history:
            skipped.append(channel.name)
            continue

        try:
            channel_id = str(channel.id)
            last_message_id = state.get(channel_id)

            # Fetch only new messages if we have a last message ID
            messages = []
            if last_message_id and not is_bootstrap:
                after_obj = discord.Object(id=int(last_message_id))
                async for msg in channel.history(limit=None, after=after_obj, oldest_first=True):
                    messages.append(msg)
            else:
                # Bootstrap — fetch everything
                async for msg in channel.history(limit=None, oldest_first=True):
                    messages.append(msg)

            if not messages:
                if not is_bootstrap:
                    exported.append(f"{channel.name} (0 new messages)")
                else:
                    skipped.append(channel.name)
                continue

            # Update state with latest message ID
            new_state[channel_id] = str(messages[-1].id)

            # Fetch reactions if requested
            reactions_map = {}
            if reactions == "yes":
                for msg in messages:
                    if msg.reactions:
                        reactions_map[str(msg.id)] = await fetch_reactions(msg)

            # Append to existing file in latest/ or create new
            ext = "txt" if format == "text" else format
            filepath = latest_dir / f"{channel.name}.{ext}"

            if format == "text":
                lines = []
                for msg in messages:
                    ts = msg.created_at.strftime("%Y-%m-%d %H:%M")
                    rxn = reactions_map.get(str(msg.id), {})
                    rxn_str = " " + " ".join(f"{e}({len(u)})" for e, u in rxn.items()) if rxn else ""
                    lines.append(f"[{ts}] {msg.author.display_name}: {msg.content}{rxn_str}")
                new_content = "\n".join(lines)
                if filepath.exists() and not is_bootstrap:
                    existing = filepath.read_text(encoding="utf-8")
                    filepath.write_text(existing + "\n" + new_content, encoding="utf-8")
                else:
                    filepath.write_text(new_content, encoding="utf-8")

            elif format == "json":
                records = [message_to_dict(msg, reactions_map.get(str(msg.id))) for msg in messages]
                if filepath.exists() and not is_bootstrap:
                    existing = json_lib.loads(filepath.read_text(encoding="utf-8"))
                    existing.extend(records)
                    filepath.write_text(json_lib.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
                else:
                    filepath.write_text(json_lib.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

            elif format == "html":
                rows = []
                for msg in messages:
                    ts = msg.created_at.strftime("%Y-%m-%d %H:%M")
                    author = discord.utils.escape_markdown(msg.author.display_name)
                    body = discord.utils.escape_markdown(msg.content).replace("\n", "<br>")
                    rxn = reactions_map.get(str(msg.id), {})
                    rxn_str = " ".join(f'<span class="rxn">{e} {len(u)}</span>' for e, u in rxn.items())
                    rows.append(
                        f'<tr><td class="ts">{ts}</td><td class="author">{author}</td>'
                        f'<td class="content">{body} {rxn_str}</td></tr>'
                    )
                new_rows = "\n".join(rows)
                if filepath.exists() and not is_bootstrap:
                    # Append rows before closing </table>
                    existing = filepath.read_text(encoding="utf-8")
                    filepath.write_text(existing.replace("</table>", new_rows + "\n</table>"), encoding="utf-8")
                else:
                    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{channel.name}</title>
<style>body{{font-family:sans-serif;background:#1e1e2e;color:#cdd6f4;padding:20px}}
table{{border-collapse:collapse;width:100%}}td{{padding:4px 8px;vertical-align:top;border-bottom:1px solid #313244}}
.ts{{color:#6c7086;white-space:nowrap;width:140px}}.author{{color:#89b4fa;width:160px;font-weight:bold}}
.content{{word-break:break-word}}.rxn{{background:#313244;border-radius:4px;padding:2px 6px;margin:2px;font-size:0.85em}}
</style></head><body>
<h2>#{channel.name}</h2><table>{new_rows}</table></body></html>"""
                    filepath.write_text(html, encoding="utf-8")

            # Download new attachments
            att_dir = latest_dir / f"{channel.name}-attachments"
            att_count = await download_attachments(messages, att_dir)
            if att_count == 0 and att_dir.exists() and not any(att_dir.iterdir()):
                att_dir.rmdir()

            # Extract new URLs
            urls_content = extract_urls(messages)
            url_count = 0
            if urls_content:
                urls_file = latest_dir / f"{channel.name}-urls.txt"
                if urls_file.exists() and not is_bootstrap:
                    existing_urls = urls_file.read_text(encoding="utf-8")
                    urls_file.write_text(existing_urls + "\n" + urls_content, encoding="utf-8")
                else:
                    urls_file.write_text(urls_content, encoding="utf-8")
                url_count = len(urls_content.splitlines())

            exported.append(
                f"{channel.name} ({len(messages)} new msgs, {att_count} att, {url_count} urls)"
            )
            log.info("export-state %s — %d new messages", channel.name, len(messages))

        except Exception:
            skipped.append(channel.name)
            log.exception("export-state failed for channel %s", channel.name)

    # Merge new state with old state and save
    state.update(new_state)
    state_file.write_text(json_lib.dumps(state, indent=2), encoding="utf-8")

    mode = "Bootstrap" if is_bootstrap else "Incremental"
    summary = (
        f"**{mode} export complete** — saved to `{latest_dir}`\n\n"
        f"**Updated ({len(exported)}):**\n" +
        "\n".join(f"• {c}" for c in exported[:40])
    )
    if len(exported) > 40:
        summary += f"\n... and {len(exported) - 40} more"
    if skipped:
        summary += f"\n\n**Skipped ({len(skipped)}):** {', '.join(skipped[:20])}"

    # DM the summary — avoids interaction token expiry on long exports
    try:
        dm = await interaction.user.create_dm()
        for chunk in split_at_sentence(summary):
            await dm.send(chunk)
        try:
            await interaction.followup.send(f"{mode} export complete — summary sent to your DMs.", ephemeral=True)
        except Exception:
            pass
    except discord.Forbidden:
        try:
            await interaction.followup.send(summary[:2000], ephemeral=True)
        except Exception:
            log.warning("Could not send export-state summary — token expired and DMs disabled")

def main():
    global retriever
    retriever = build_retriever()
    log.info("Retriever ready")
    client.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()