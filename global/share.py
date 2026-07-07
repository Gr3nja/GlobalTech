import io
import re
from typing import Dict, Optional

import discord
from discord.ext import commands

from .set import load_channels
from .user import get_display_name, get_avatar_url, get_guild_name
from .check import schedule_result_reaction
from .ban import is_banned

# Discordの仕様でWebhookのusernameに含められない文字列(大文字小文字問わず)
FORBIDDEN_USERNAME_WORDS = ["discord", "clyde"]


def sanitize_webhook_username(username: str) -> str:
    """
    Discordの Webhook username 制約に適合するように整形する。
    - "discord" "clyde" という文字列を含められない(大文字小文字問わず)
    - 前後の空白は使用不可
    - 空文字列は使用不可
    - 最大80文字
    """
    sanitized = username

    for word in FORBIDDEN_USERNAME_WORDS:
        # 例: "discord" -> "d*scord" のように一部の文字を置き換えて回避する
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        sanitized = pattern.sub(word[0] + "*" * (len(word) - 2) + word[-1], sanitized)

    sanitized = sanitized.strip()

    if not sanitized:
        sanitized = "Unknown User"

    return sanitized[:80]


REPLY_SNIPPET_LENGTH = 50


async def build_reply_prefix(message: discord.Message) -> str:
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
        ref_author = get_display_name(resolved.author)

    ref_content = resolved.content.replace("\n", " ").strip()
    if not ref_content:
        ref_content = "(添付ファイルのみ)" if resolved.attachments else "(内容なし)"
    if len(ref_content) > REPLY_SNIPPET_LENGTH:
        ref_content = ref_content[:REPLY_SNIPPET_LENGTH] + "…"

    return f"> **{ref_author}**: {ref_content}\n"


async def get_or_create_webhook(channel: discord.TextChannel) -> Optional[discord.Webhook]:
    """指定チャンネルの GlobalChatWebhook を取得、なければ新規作成する"""
    try:
        webhooks = await channel.webhooks()
    except discord.Forbidden:
        print(f"[WARN] webhooks()取得失敗(権限不足): channel={channel.id} ({channel.name})")
        return None
    except discord.HTTPException as e:
        print(f"[WARN] webhooks()取得失敗: channel={channel.id} ({channel.name}) error={e}")
        return None

    webhook = discord.utils.get(webhooks, name="GlobalChatWebhook")

    # channel.webhooks() で取得したWebhookが自分(Bot)以外の作成物だと token を持たず
    # webhook.send() が失敗するため、その場合は無視して作り直す
    if webhook is not None and webhook.token is None:
        webhook = None

    if webhook is None:
        try:
            webhook = await channel.create_webhook(name="GlobalChatWebhook")
        except discord.Forbidden:
            print(f"[WARN] webhook作成失敗(権限不足): channel={channel.id} ({channel.name})")
            return None
        except discord.HTTPException as e:
            # 例: 1チャンネルあたりのWebhook上限(15個)超過など
            print(f"[WARN] webhook作成失敗: channel={channel.id} ({channel.name}) error={e}")
            return None

    return webhook


async def broadcast_message(
    bot: commands.Bot,
    content: str,
    username: str,
    avatar_url: Optional[str] = None,
    exclude_channel_id: Optional[int] = None,
) -> None:
    """任意のメッセージを登録済みの全チャンネルにWebhook経由で送信する汎用関数。
    global/joinlog.py の参加/脱退通知などから利用される。
    """
    channels = load_channels()

    for channel_id in channels:
        if channel_id == exclude_channel_id:
            continue

        channel = bot.get_channel(channel_id)
        if channel is None:
            continue

        webhook = await get_or_create_webhook(channel)
        if webhook is None:
            continue

        try:
            await webhook.send(
                content=content,
                username=sanitize_webhook_username(username),
                avatar_url=avatar_url,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as e:
            print(f"[WARN] webhook送信失敗(broadcast): channel={channel_id} error={e}")
            continue


class ShareCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # チャンネルごとに作成したWebhookをキャッシュしておく
        self.webhook_cache: Dict[int, discord.Webhook] = {}

    async def _get_cached_webhook(
        self, channel: discord.TextChannel
    ) -> Optional[discord.Webhook]:
        if channel.id in self.webhook_cache:
            return self.webhook_cache[channel.id]

        webhook = await get_or_create_webhook(channel)
        if webhook is not None:
            self.webhook_cache[channel.id] = webhook
        return webhook

    def _invalidate_cached_webhook(self, channel_id: int) -> None:
        """Webhookが手動削除されている等で送信に失敗した場合、キャッシュを破棄して
        次回送信時に再作成させる。"""
        self.webhook_cache.pop(channel_id, None)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Bot自身や他のBotのメッセージは無視
        if message.author.bot:
            return
        # DMは対象外
        if not message.guild:
            return

        channels = load_channels()
        if message.channel.id not in channels:
            return

        # グローバルチャットBANされているユーザーのメッセージは転送せず、削除する
        if is_banned(message.author.id):
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            return

        content = message.content
        if not content and not message.attachments:
            return

        reply_prefix = await build_reply_prefix(message)
        full_content = f"{reply_prefix}{content}" if (reply_prefix or content) else None

        # 添付ファイルはあらかじめ読み込んで、各チャンネル送信で使い回す
        attachments_data = []
        for attachment in message.attachments:
            data = await attachment.read()
            attachments_data.append((data, attachment.filename))

        username = f"{get_display_name(message.author)} ({get_guild_name(message.author)})"
        avatar_url = get_avatar_url(message.author)

        target_count = 0
        success_count = 0

        for channel_id in channels:
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
                    username=sanitize_webhook_username(username),
                    avatar_url=avatar_url,
                    files=files,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                success_count += 1
            except discord.NotFound:
                # Webhookが手動削除されている等。キャッシュを破棄して次回再作成させる。
                print(f"[WARN] Webhookが見つかりません(削除された可能性): channel={channel_id}")
                self._invalidate_cached_webhook(channel_id)
                continue
            except discord.HTTPException as e:
                print(f"[WARN] webhook送信失敗: channel={channel_id} error={e}")
                continue

        # 他に転送先サーバーがある場合のみ、送信結果のリアクションを付ける
        if target_count > 0:
            schedule_result_reaction(message, success=success_count > 0)


async def setup(bot: commands.Bot):
    await bot.add_cog(ShareCog(bot))