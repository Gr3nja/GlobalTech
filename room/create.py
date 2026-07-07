import json
import os
from typing import Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .password import hash_password

# room.json はプロジェクトのルート(main.pyと同じ階層)に生成されます
ROOM_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "room.json")
)


def load_rooms() -> Dict[str, dict]:
    """
    ルーム情報を読み込む。
    形式: {
      "ルーム名": {
        "owner_id": int,
        "password_hash": str または null,
        "channels": [channel_id, ...]
      }
    }
    """
    if not os.path.exists(ROOM_FILE):
        return {}
    with open(ROOM_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {}
    return data.get("rooms", {})


def save_rooms(rooms: Dict[str, dict]) -> None:
    with open(ROOM_FILE, "w", encoding="utf-8") as f:
        json.dump({"rooms": rooms}, f, ensure_ascii=False, indent=2)


def get_room_by_channel(channel_id: int) -> Optional[str]:
    """指定したチャンネルが参加しているルーム名を返す(参加していなければNone)"""
    rooms = load_rooms()
    for room_name, room_data in rooms.items():
        if channel_id in room_data.get("channels", []):
            return room_name
    return None


class RoomCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    room_group = app_commands.Group(
        name="room", description="自分専用のルームチャットを作成・管理します。"
    )

    @room_group.command(
        name="create", description="新しいルームを作成し、このチャンネルを参加させます。"
    )
    @app_commands.describe(
        roomname="作成するルーム名",
        password="ルームのパスワード(任意。設定すると他人が勝手に参加できなくなります)",
    )
    async def room_create(
        self,
        interaction: discord.Interaction,
        roomname: str,
        password: Optional[str] = None,
    ):
        rooms = load_rooms()

        if roomname in rooms:
            await interaction.response.send_message(
                f"ルーム「{roomname}」は既に存在します。別の名前を指定してください。",
                ephemeral=True,
            )
            return

        rooms[roomname] = {
            "owner_id": interaction.user.id,
            "password_hash": hash_password(password) if password else None,
            "channels": [interaction.channel_id],
        }
        save_rooms(rooms)

        message = f"✅ ルーム「{roomname}」を作成し、このチャンネルを参加させました。"
        if password:
            message += "\n🔒 パスワードが設定されました。参加にはこのパスワードが必要です。"
        await interaction.response.send_message(message, ephemeral=True)

    @room_group.command(
        name="delete", description="ルームを削除します(作成者のみ実行できます)。"
    )
    @app_commands.describe(roomname="削除するルーム名")
    async def room_delete(self, interaction: discord.Interaction, roomname: str):
        # 循環importを避けるため、関数内でimportする
        from .delete import handle_delete

        await handle_delete(interaction, roomname)

    @room_group.command(
        name="join", description="既存のルームにこのチャンネルを参加させます。"
    )
    @app_commands.describe(
        roomname="参加するルーム名",
        password="ルームにパスワードが設定されている場合は入力してください",
    )
    async def room_join(
        self,
        interaction: discord.Interaction,
        roomname: str,
        password: Optional[str] = None,
    ):
        # 循環importを避けるため、関数内でimportする
        from .join import handle_join

        await handle_join(interaction, roomname, password)

    @room_group.command(
        name="list", description="現在存在するルームの一覧を表示します。"
    )
    async def room_list(self, interaction: discord.Interaction):
        rooms = load_rooms()

        if not rooms:
            await interaction.response.send_message(
                "現在、作成されているルームはありません。", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📋 ルーム一覧",
            color=discord.Color.blurple(),
            description=f"合計 {len(rooms)} 個のルームがあります。",
        )

        for name, data in rooms.items():
            owner_id = data.get("owner_id")
            channel_count = len(data.get("channels", []))
            has_password = "🔒 あり" if data.get("password_hash") else "🔓 なし"
            embed.add_field(
                name=f"🏠 {name}",
                value=(
                    f"作成者: <@{owner_id}>\n"
                    f"参加チャンネル数: {channel_count}\n"
                    f"パスワード: {has_password}"
                ),
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RoomCog(bot))