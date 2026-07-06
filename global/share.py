import io
from typing import Dict, Optional

import discord
from discord.ext import commands

from .set import load_channels
from .user import get_display_name, get_avatar_url, get_guild_name
from .check import schedule_result_reaction


async def get_or_create_webhook(channel: discord.TextChannel) -> Optional[discord.Webhook]:
    """指定チャンネルの GlobalChatWebhook を取得、なければ新規作成する"""
    try:
        webhooks = await channel.webhooks()
    except discord.Forbidden:
        return None

    webhook = discord.utils.get(webhooks, name="GlobalChatWebhook")

    if webhook is None:
        try:
            webhook = await channel.create_webhook(name="GlobalChatWebhook")
        except discord.Forbidden:
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
                username=username,
                avatar_url=avatar_url,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
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

        content = message.content
        if not content and not message.attachments:
            return

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
                    content=content if content else None,
                    username=username,
                    avatar_url=avatar_url,
                    files=files,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                success_count += 1
            except discord.HTTPException:
                continue

        # 他に転送先サーバーがある場合のみ、送信結果のリアクションを付ける
        if target_count > 0:
            schedule_result_reaction(message, success=success_count > 0)


async def setup(bot: commands.Bot):
    await bot.add_cog(ShareCog(bot))