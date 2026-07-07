import asyncio
import io
from typing import Dict, Optional

import discord
from discord.ext import commands

from .create import load_rooms, save_rooms, get_room_by_channel
from .password import verify_password

ROOM_WEBHOOK_NAME = "RoomChatWebhook"
REACTION_DURATION_SECONDS = 3

# Discordの仕様でWebhookのusernameに含められない文字列(大文字小文字問わず)
FORBIDDEN_USERNAME_WORDS = ("discord", "clyde")


async def handle_join(
    interaction: discord.Interaction,
    roomname: str,
    password: Optional[str] = None,
) -> None:
    """指定したルームにこのチャンネルを参加させる(1チャンネル1ルームまで)"""
    rooms = load_rooms()

    if roomname not in rooms:
        await interaction.response.send_message(
            f"ルーム「{roomname}」は存在しません。", ephemeral=True
        )
        return

    room = rooms[roomname]
    password_hash = room.get("password_hash")

    if password_hash:
        if not password or not verify_password(password, password_hash):
            await interaction.response.send_message(
                "パスワードが違います。", ephemeral=True
            )
            return

    channel_id = interaction.channel_id

    if channel_id in room.get("channels", []):
        await interaction.response.send_message(
            f"このチャンネルは既にルーム「{roomname}」に参加しています。",
            ephemeral=True,
        )
        return

    # このチャンネルが既に別のルームに参加している場合は、自動的に脱退させる
    previous_room = None
    for name, data in rooms.items():
        if name != roomname and channel_id in data.get("channels", []):
            previous_room = name
            data["channels"].remove(channel_id)
            break

    room.setdefault("channels", []).append(channel_id)
    save_rooms(rooms)

    message = f"✅ ルーム「{roomname}」に参加しました。"
    if previous_room is not None:
        message += f"\n(以前参加していたルーム「{previous_room}」からは自動的に退出しました)"
    await interaction.response.send_message(message, ephemeral=True)


def _sanitize_webhook_username(username: str) -> str:
    """Discordの Webhook username 制約("discord"/"clyde"を含められない等)に適合させる"""
    sanitized = username
    for word in FORBIDDEN_USERNAME_WORDS:
        idx = sanitized.lower().find(word)
        while idx != -1:
            sanitized = (
                sanitized[:idx]
                + word[0] + "*" * (len(word) - 2) + word[-1]
                + sanitized[idx + len(word):]
            )
            idx = sanitized.lower().find(word)
    sanitized = sanitized.strip()
    return sanitized[:80] if sanitized else "Unknown User"


REPLY_SNIPPET_LENGTH = 50


def _get_display_name(user: discord.abc.User) -> str:
    if isinstance(user, discord.Member) and user.nick:
        return user.nick
    return user.display_name


async def _build_reply_prefix(message: discord.Message) -> str:
    """
    メッセージが返信(reply)の場合、引用形式のプレフィックス文字列を生成する。
    返信でない場合、または元メッセージが取得できない場合は空文字列を返す。
    """
    if message.reference is None:
        return ""

    resolved = message.reference.resolved

    if resolved is None and message.reference.message_id:
        try:
            resolved = await message.channel.fetch_message(message.reference.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            resolved = None

    if not isinstance(resolved, discord.Message):
        return "> *(元のメッセージは取得できませんでした)*\n"

    # Webhook経由の転送メッセージの場合は author.bot が True になり、
    # username(なりすまし表示名)がそのまま元の発言者名になっている
    if resolved.author.bot:
        ref_author = resolved.author.name
    else:
        ref_author = _get_display_name(resolved.author)

    ref_content = resolved.content.replace("\n", " ").strip()
    if not ref_content:
        ref_content = "(添付ファイルのみ)" if resolved.attachments else "(内容なし)"
    if len(ref_content) > REPLY_SNIPPET_LENGTH:
        ref_content = ref_content[:REPLY_SNIPPET_LENGTH] + "…"

    return f"> **{ref_author}**: {ref_content}\n"


async def _get_or_create_room_webhook(
    channel: discord.TextChannel,
) -> Optional[discord.Webhook]:
    try:
        webhooks = await channel.webhooks()
    except discord.Forbidden:
        print(f"[WARN][room] webhooks()取得失敗(権限不足): channel={channel.id} ({channel.name})")
        return None
    except discord.HTTPException as e:
        print(f"[WARN][room] webhooks()取得失敗: channel={channel.id} ({channel.name}) error={e}")
        return None

    webhook = discord.utils.get(webhooks, name=ROOM_WEBHOOK_NAME)

    if webhook is None:
        try:
            webhook = await channel.create_webhook(name=ROOM_WEBHOOK_NAME)
        except discord.Forbidden:
            print(f"[WARN][room] webhook作成失敗(権限不足): channel={channel.id} ({channel.name})")
            return None
        except discord.HTTPException as e:
            print(f"[WARN][room] webhook作成失敗: channel={channel.id} ({channel.name}) error={e}")
            return None

    return webhook


async def _add_temporary_reaction(
    message: discord.Message, success: bool, duration: float = REACTION_DURATION_SECONDS
) -> None:
    emoji = "✅" if success else "❌"
    try:
        await message.add_reaction(emoji)
    except discord.HTTPException:
        return

    await asyncio.sleep(duration)

    try:
        if message.guild is not None and message.guild.me is not None:
            await message.remove_reaction(emoji, message.guild.me)
        else:
            await message.remove_reaction(emoji, message.author)
    except discord.HTTPException:
        pass


def _schedule_result_reaction(message: discord.Message, success: bool) -> None:
    asyncio.create_task(_add_temporary_reaction(message, success))


class RoomShareCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # チャンネルごとに作成したWebhookをキャッシュしておく
        self.webhook_cache: Dict[int, discord.Webhook] = {}

    async def _get_cached_webhook(
        self, channel: discord.TextChannel
    ) -> Optional[discord.Webhook]:
        if channel.id in self.webhook_cache:
            return self.webhook_cache[channel.id]

        webhook = await _get_or_create_room_webhook(channel)
        if webhook is not None:
            self.webhook_cache[channel.id] = webhook
        return webhook

    def _invalidate_cached_webhook(self, channel_id: int) -> None:
        self.webhook_cache.pop(channel_id, None)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Bot自身や他のBotのメッセージは無視
        if message.author.bot:
            return
        # DMは対象外
        if not message.guild:
            return

        room_name = get_room_by_channel(message.channel.id)
        if room_name is None:
            return

        rooms = load_rooms()
        room = rooms.get(room_name)
        if room is None:
            return

        content = message.content
        if not content and not message.attachments:
            return

        reply_prefix = await _build_reply_prefix(message)
        full_content = f"{reply_prefix}{content}" if (reply_prefix or content) else None

        # 添付ファイルはあらかじめ読み込んで、各チャンネル送信で使い回す
        attachments_data = []
        for attachment in message.attachments:
            data = await attachment.read()
            attachments_data.append((data, attachment.filename))

        if isinstance(message.author, discord.Member) and message.author.nick:
            display_name = message.author.nick
        else:
            display_name = message.author.display_name
        guild_name = message.guild.name

        username = _sanitize_webhook_username(f"{display_name} ({guild_name})")
        avatar_url = message.author.display_avatar.url

        target_count = 0
        success_count = 0

        for channel_id in room.get("channels", []):
            if channel_id == message.channel.id:
                continue

            target_count += 1

            target_channel = self.bot.get_channel(channel_id)
            if target_channel is None:
                continue

            webhook = await self._get_cached_webhook(target_channel)
            if webhook is None:
                continue

            files = [
                discord.File(io.BytesIO(data), filename=name)
                for data, name in attachments_data
            ]

            try:
                await webhook.send(
                    content=full_content,
                    username=username,
                    avatar_url=avatar_url,
                    files=files,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                success_count += 1
            except discord.NotFound:
                print(f"[WARN][room] Webhookが見つかりません(削除された可能性): channel={channel_id}")
                self._invalidate_cached_webhook(channel_id)
                continue
            except discord.HTTPException as e:
                print(f"[WARN][room] webhook送信失敗: channel={channel_id} error={e}")
                continue

        # 他に転送先チャンネルがある場合のみ、送信結果のリアクションを付ける
        if target_count > 0:
            _schedule_result_reaction(message, success=success_count > 0)


async def setup(bot: commands.Bot):
    await bot.add_cog(RoomShareCog(bot))