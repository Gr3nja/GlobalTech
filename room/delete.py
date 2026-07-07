import discord

from .create import load_rooms, save_rooms


async def handle_delete(interaction: discord.Interaction, roomname: str) -> None:
    """
    ルームを削除する。
    削除できるのは、そのルームの作成者(owner_id)のみ。
    パスワードは削除の可否には使用しない。
    """
    rooms = load_rooms()

    if roomname not in rooms:
        await interaction.response.send_message(
            f"ルーム「{roomname}」は存在しません。", ephemeral=True
        )
        return

    room = rooms[roomname]

    if interaction.user.id != room.get("owner_id"):
        await interaction.response.send_message(
            "このルームを削除できるのは作成者のみです。", ephemeral=True
        )
        return

    del rooms[roomname]
    save_rooms(rooms)

    await interaction.response.send_message(
        f"🗑️ ルーム「{roomname}」を削除しました。", ephemeral=True
    )
