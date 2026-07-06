import discord
from discord import app_commands
from discord.ext import commands


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Botの使い方を表示します。")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="グローバルチャットBot ヘルプ",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="/global",
            value="このチャンネルをグローバルチャットに設定/解除します。",
            inline=False,
        )
        embed.add_field(
            name="!global_ban {ユーザー} {理由}",
            value="ユーザーをグローバルチャットからBANします(管理者のみ)。",
            inline=False,
        )
        embed.add_field(
            name="!global_unban {ユーザー}",
            value="BANを解除します(管理者のみ)。",
            inline=False,
        )
        embed.add_field(
            name="送信結果の確認",
            value="メッセージ送信後、✅(成功)または❌(失敗)が一時的に表示されます。",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))