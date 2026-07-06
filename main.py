import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

# .env ファイルから環境変数を読み込む
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.check
def block_dm_prefix_commands(ctx: commands.Context) -> bool:
    """!から始まるコマンド(!global_banなど)をDMでは実行できないようにする"""
    return ctx.guild is not None


async def block_dm_slash_commands(interaction: discord.Interaction) -> bool:
    """スラッシュコマンド(/globalなど)をDMでは実行できないようにする"""
    if interaction.guild is None:
        await interaction.response.send_message(
            "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
        )
        return False
    return True


# CommandTreeのinteraction_checkを上書きして、DMでのスラッシュコマンド実行を禁止する
bot.tree.interaction_check = block_dm_slash_commands


# 読み込むCog(拡張機能)の一覧
INITIAL_EXTENSIONS = [
    "global.set",
    "global.share",
    "global.joinlog",
    "global.ban",
    "global.help",
]


@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user} (ID: {bot.user.id})")

    # Botのステータスメッセージを設定(種類表示なしでテキストのみ)
    await bot.change_presence(
        status=discord.Status.online,  # online / idle / dnd / invisible
        activity=discord.CustomActivity(name="/global | グローバルチャット"),
    )

    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンドを{len(synced)}個同期しました。")
    except Exception as e:
        print(f"スラッシュコマンドの同期に失敗しました: {e}")
    print("Botの準備が完了しました。")


async def main():
    async with bot:
        for extension in INITIAL_EXTENSIONS:
            await bot.load_extension(extension)

        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise RuntimeError(
                "環境変数 DISCORD_TOKEN が設定されていません。"
                "Botのトークンを環境変数に設定してから起動してください。"
            )
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())