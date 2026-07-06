from typing import Optional

import discord
from discord.ext import commands

from .set import load_channels, save_channels
from .share import broadcast_message


async def notify_join(
    bot: commands.Bot,
    guild: discord.Guild,
    exclude_channel_id: Optional[int] = None,
) -> None:
    """サーバーがグローバルチャットに参加したことを、登録済みの全チャンネルに通知する"""
    avatar_url = guild.icon.url if guild.icon else None
    await broadcast_message(
        bot,
        content=f" **{guild.name}** が参加しました。",
        username=guild.name,
        avatar_url=avatar_url,
        exclude_channel_id=exclude_channel_id,
    )


async def notify_leave(
    bot: commands.Bot,
    guild: discord.Guild,
    exclude_channel_id: Optional[int] = None,
) -> None:
    """サーバーがグローバルチャットから脱退したことを、登録済みの全チャンネルに通知する"""
    avatar_url = guild.icon.url if guild.icon else None
    await broadcast_message(
        bot,
        content=f" **{guild.name}** が脱退しました。",
        username=guild.name,
        avatar_url=avatar_url,
        exclude_channel_id=exclude_channel_id,
    )


class JoinLogCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """Botがサーバーから追放/退出させられた際に、登録チャンネルを自動解除して脱退を通知する"""
        channels = load_channels()
        guild_channel_ids = {c.id for c in guild.channels}
        removed_ids = [cid for cid in channels if cid in guild_channel_ids]

        if not removed_ids:
            return

        for cid in removed_ids:
            channels.remove(cid)
        save_channels(channels)

        await notify_leave(self.bot, guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(JoinLogCog(bot))