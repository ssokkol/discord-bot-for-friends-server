import discord
from discord.ext import commands
from typing import List, Tuple
from .base_command import BaseCommand
from ..database import TopDatabase
from ..utils import format_time


class TopCommands(BaseCommand):
    """Класс для команд топов"""

    def __init__(self, bot: commands.Bot, top_db: TopDatabase):
        super().__init__(bot)
        self.top_db = top_db

    def _get_display_name(self, guild: discord.Guild, user_id: int) -> str:
        """Get member display name without mentioning"""
        member = guild.get_member(user_id)
        return member.display_name if member else f"Пользователь {user_id}"

    async def show_voice_top(self, interaction: discord.Interaction, limit: int = 5) -> None:
        """Показывает топ по времени в голосовых каналах"""
        try:
            top_data = await self.top_db.get_voice_top(limit)

            if not top_data:
                await interaction.response.send_message('Нет данных для отображения топа', ephemeral=True)
                return

            embed = discord.Embed(title="Топ по голосовому онлайну", color=discord.Color.blue())
            lines = []
            for i, (user_id, voice_time) in enumerate(top_data, 1):
                name = self._get_display_name(interaction.guild, user_id)
                formatted_time = format_time(voice_time)
                lines.append(f"**{i}.** {name} — `{formatted_time}`")

            embed.description = "\n".join(lines)
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(f'Ошибка при получении топа: {e}', ephemeral=True)

    async def show_messages_top(self, interaction: discord.Interaction, limit: int = 5) -> None:
        """Показывает топ по сообщениям"""
        try:
            top_data = await self.top_db.get_messages_top(limit)

            if not top_data:
                await interaction.response.send_message('Нет данных для отображения топа', ephemeral=True)
                return

            embed = discord.Embed(title="Топ по сообщениям", color=discord.Color.green())
            lines = []
            for i, (user_id, messages) in enumerate(top_data, 1):
                name = self._get_display_name(interaction.guild, user_id)
                lines.append(f"**{i}.** {name} — `{messages}` сообщений")

            embed.description = "\n".join(lines)
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(f'Ошибка при получении топа: {e}', ephemeral=True)

    async def show_level_top(self, interaction: discord.Interaction, limit: int = 5) -> None:
        """Показывает топ по уровням"""
        try:
            top_data = await self.top_db.get_level_top(limit)

            if not top_data:
                await interaction.response.send_message('Нет данных для отображения топа', ephemeral=True)
                return

            embed = discord.Embed(title="Топ по уровням", color=discord.Color.gold())
            lines = []
            for i, (user_id, level, xp) in enumerate(top_data, 1):
                name = self._get_display_name(interaction.guild, user_id)
                lines.append(f"**{i}.** {name} — Уровень `{level}` ({xp} XP)")

            embed.description = "\n".join(lines)
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(f'Ошибка при получении топа: {e}', ephemeral=True)

    async def show_general_top(self, interaction: discord.Interaction, top_type: str, limit: int = 5) -> None:
        """Показывает общий топ по указанному типу"""
        try:
            if top_type == "voice":
                await self.show_voice_top(interaction, limit)
            elif top_type == "messages":
                await self.show_messages_top(interaction, limit)
            elif top_type == "level":
                await self.show_level_top(interaction, limit)
            else:
                await interaction.response.send_message('Неизвестный тип топа. Доступные: voice, messages, level', ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f'Ошибка при получении топа: {e}', ephemeral=True)
