import json
import os

import discord
from discord import app_commands
from discord.ext import commands

# channel.json はプロジェクトのルート(main.pyと同じ階層)に生成されます
CHANNEL_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "channel.json")
)


def load_channels() -> list:
    """登録済みチャンネルIDのリストを読み込む"""
    if not os.path.exists(CHANNEL_FILE):
        return []
    with open(CHANNEL_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return []
    return data.get("channels", [])


def save_channels(channels: list) -> None:
    """チャンネルIDのリストをchannel.jsonに保存する"""
    with open(CHANNEL_FILE, "w", encoding="utf-8") as f:
        json.dump({"channels": channels}, f, ensure_ascii=False, indent=2)


class SetCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="global",
        description="このチャンネルをグローバルチャットに設定/解除します。",
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def global_command(self, interaction: discord.Interaction):
        # 循環importを避けるため、関数内でimportする
        from .joinlog import notify_join, notify_leave

        channels = load_channels()
        channel_id = interaction.channel_id
        guild = interaction.guild

        if channel_id in channels:
            # 既に登録済みなら解除
            channels.remove(channel_id)
            save_channels(channels)
            await interaction.response.send_message(
                "このチャンネルをグローバルチャットから解除しました。",
                ephemeral=True,
            )
            if guild is not None:
                await notify_leave(self.bot, guild, exclude_channel_id=channel_id)
        else:
            # 未登録なら新規登録
            channels.append(channel_id)
            save_channels(channels)
            await interaction.response.send_message(
                "このチャンネルをグローバルチャットに設定しました！",
                ephemeral=True,
            )
            if guild is not None:
                await notify_join(self.bot, guild)

    @global_command.error
    async def global_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "このコマンドを実行するには「チャンネルの管理」権限が必要です。",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"エラーが発生しました: {error}", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(SetCog(bot))