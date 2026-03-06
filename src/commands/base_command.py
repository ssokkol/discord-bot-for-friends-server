import discord
from discord.ext import commands


class BaseCommand:
    """Базовый класс для всех команд бота"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def is_admin(self, member: discord.Member) -> bool:
        """Проверяет, является ли пользователь администратором (LVL0/LVL1)"""
        config = self.bot.config
        return (
            member.id == int(config.ADMIN_USER_ID) or
            any(role.id in [config.ADMIN_ROLE_LVL0, config.ADMIN_ROLE_LVL1] for role in member.roles)
        )

    def is_owner(self, member: discord.Member) -> bool:
        """Проверяет, является ли пользователь главным админом (ADMIN_USER_ID или LVL0)"""
        config = self.bot.config
        return (
            member.id == int(config.ADMIN_USER_ID) or
            any(role.id == config.ADMIN_ROLE_LVL0 for role in member.roles)
        )
