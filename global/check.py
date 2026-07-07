import asyncio

import discord

SUCCESS_EMOJI = "✅"
FAILURE_EMOJI = "❌"
REACTION_DURATION_SECONDS = 3


async def add_temporary_reaction(
    message: discord.Message,
    success: bool,
    duration: float = REACTION_DURATION_SECONDS,
) -> None:
    """
    メッセージの転送結果に応じて✅/❌のリアクションを付け、
    一定時間後に自動で取り消す。

    success=True  -> ✅ を付ける(他サーバーへの送信に成功)
    success=False -> ❌ を付ける(他サーバーへの送信に失敗)
    """
    emoji = SUCCESS_EMOJI if success else FAILURE_EMOJI

    try:
        await message.add_reaction(emoji)
    except discord.HTTPException:
        # リアクションを付けられなくても、他の処理には影響させない
        return

    await asyncio.sleep(duration)

    try:
        if message.guild is not None and message.guild.me is not None:
            await message.remove_reaction(emoji, message.guild.me)
        else:
            await message.remove_reaction(emoji, message.author)
    except discord.HTTPException:
        # メッセージが削除された等でリアクション解除に失敗しても無視する
        pass


def schedule_result_reaction(message: discord.Message, success: bool) -> None:
    """
    add_temporary_reaction をバックグラウンドタスクとして実行する。
    on_message 内で await すると3秒待たされてしまうため、
    処理をブロックしないようにタスク化して呼び出す。
    """
    asyncio.create_task(add_temporary_reaction(message, success))