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

# 読み込むCog(拡張機能)の一覧
INITIAL_EXTENSIONS = [
    "global.set",
    "global.share",
    "global.joinlog",
]


@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user} (ID: {bot.user.id})")
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