from typing import Union

import discord


def get_display_name(member: Union[discord.Member, discord.User]) -> str:
    """表示名を返す(サーバーのニックネームがあればそれ、なければユーザー名)"""
    if isinstance(member, discord.Member) and member.nick:
        return member.nick
    return member.display_name


def get_avatar_url(member: Union[discord.Member, discord.User]) -> str:
    """アイコンのURLを返す(アイコン未設定の場合はデフォルトアイコン)"""
    return member.display_avatar.url


def get_guild_name(member: Union[discord.Member, discord.User]) -> str:
    """メッセージ送信元のサーバー名を返す(取得できない場合はDM扱い)"""
    if isinstance(member, discord.Member) and member.guild:
        return member.guild.name
    return "DM"