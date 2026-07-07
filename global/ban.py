import json
import os
import time
from typing import Dict, Set

import discord
from discord.ext import commands

# ban.json はプロジェクトのルート(main.pyと同じ階層)に生成されます
BAN_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "ban.json")
)


def _get_admin_ids() -> Set[int]:
    """
    .env の GLOBAL_BAN_ADMINS (カンマ区切りのユーザーID) を読み込む。
    例: GLOBAL_BAN_ADMINS=123456789012345678,234567890123456789
    """
    raw = os.getenv("GLOBAL_BAN_ADMINS", "")
    admin_ids: Set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            admin_ids.add(int(part))
    return admin_ids


def load_bans() -> Dict[str, dict]:
    """
    BANされたユーザー情報を読み込む。
    形式: { "ユーザーID(文字列)": {"username":..., "reason":..., "banned_by":..., "banned_at":...} }
    """
    if not os.path.exists(BAN_FILE):
        return {}
    with open(BAN_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {}
    return data


def save_bans(data: Dict[str, dict]) -> None:
    with open(BAN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_banned(user_id: int) -> bool:
    """指定したユーザーIDがグローバルチャットBANされているか判定する"""
    bans = load_bans()
    return str(user_id) in bans


class BanCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_admin(self, user_id: int) -> bool:
        return user_id in _get_admin_ids()

    @commands.command(name="global_ban")
    async def global_ban(
        self,
        ctx: commands.Context,
        user: discord.User,
        *,
        reason: str = "理由なし",
    ):
        """使い方: !global_ban {ユーザー(メンション/ID)} {理由}"""
        if not self._is_admin(ctx.author.id):
            await ctx.reply("このコマンドを使用する権限がありません。")
            return

        bans = load_bans()
        bans[str(user.id)] = {
            "username": str(user),
            "reason": reason,
            "banned_by": str(ctx.author),
            "banned_by_id": ctx.author.id,
            "banned_at": time.time(),
        }
        save_bans(bans)

        await ctx.reply(
            f"🚫 **{user}** をグローバルチャットからBANしました。\n理由: {reason}"
        )

    @global_ban.error
    async def global_ban_error(
        self, ctx: commands.Context, error: commands.CommandError
    ):
        if isinstance(error, commands.UserNotFound):
            await ctx.reply(
                "指定されたユーザーが見つかりませんでした。"
                "メンションまたはユーザーIDで指定してください。"
            )
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply("使い方: `!global_ban {ユーザー} {理由}`")
        else:
            await ctx.reply(f"エラーが発生しました: {error}")

    @commands.command(name="global_unban")
    async def global_unban(self, ctx: commands.Context, user: discord.User):
        """使い方: !global_unban {ユーザー(メンション/ID)}"""
        if not self._is_admin(ctx.author.id):
            await ctx.reply("このコマンドを使用する権限がありません。")
            return

        bans = load_bans()
        if str(user.id) not in bans:
            await ctx.reply(f"**{user}** はBANされていません。")
            return

        del bans[str(user.id)]
        save_bans(bans)
        await ctx.reply(f"✅ **{user}** のグローバルチャットBANを解除しました。")

    @global_unban.error
    async def global_unban_error(
        self, ctx: commands.Context, error: commands.CommandError
    ):
        if isinstance(error, commands.UserNotFound):
            await ctx.reply("指定されたユーザーが見つかりませんでした。")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply("使い方: `!global_unban {ユーザー}`")
        else:
            await ctx.reply(f"エラーが発生しました: {error}")


async def setup(bot: commands.Bot):
    await bot.add_cog(BanCog(bot))