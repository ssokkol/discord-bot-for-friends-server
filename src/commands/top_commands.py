import discord
from discord.ext import commands
from typing import List, Tuple
from .base_command import BaseCommand
from ..database import TopDatabase
from ..utils import format_time, format_money


class TopCommands(BaseCommand):
    """Класс для команд топов"""

    def __init__(self, bot: commands.Bot, top_db: TopDatabase):
        super().__init__(bot)
        self.top_db = top_db

    async def show_voice_top(self, interaction: discord.Interaction, limit: int = 5) -> None:
        """Показывает топ по времени в голосовых каналах"""
        try:
            top_data = await self.top_db.get_voice_top(limit)

            if not top_data:
                await interaction.response.send_message('Нет данных для отображения топа')
                return

            top_list = []
            for i, (user_id, voice_time) in enumerate(top_data, 1):
                formatted_time = format_time(voice_time)
                top_list.append(f'**{i}. <@{user_id}> время - `{formatted_time}`**\n')

            await interaction.response.send_message(''.join(top_list))

        except Exception as e:
            await interaction.response.send_message(f'Ошибка при получении топа: {e}', ephemeral=True)

    async def show_messages_top(self, interaction: discord.Interaction, limit: int = 5) -> None:
        """Показывает топ по сообщениям"""
        try:
            top_data = await self.top_db.get_messages_top(limit)

            if not top_data:
                await interaction.response.send_message('Нет данных для отображения топа')
                return

            top_list = []
            for i, (user_id, messages) in enumerate(top_data, 1):
                top_list.append(f'**{i}. <@{user_id}> сообщений - `{messages}`**\n')

            await interaction.response.send_message(''.join(top_list))

        except Exception as e:
            await interaction.response.send_message(f'Ошибка при получении топа: {e}', ephemeral=True)

    async def show_balance_top(self, interaction: discord.Interaction, limit: int = 5) -> None:
        """Показывает топ по балансу"""
        try:
            top_data = await self.top_db.get_balance_top(limit)

            if not top_data:
                await interaction.response.send_message('Нет данных для отображения топа')
                return

            top_list = []
            for i, (user_id, money) in enumerate(top_data, 1):
                formatted_money = format_money(money)
                top_list.append(f'**{i}. <@{user_id}> баланс - `{formatted_money}руб`**\n')

            await interaction.response.send_message(''.join(top_list))

        except Exception as e:
            await interaction.response.send_message(f'Ошибка при получении топа: {e}', ephemeral=True)

    async def show_general_top(self, interaction: discord.Interaction, top_type: str, limit: int = 5) -> None:
        """Показывает общий топ по указанному типу"""
        try:
            if top_type == "voice":
                await self.show_voice_top(interaction, limit)
            elif top_type == "messages":
                await self.show_messages_top(interaction, limit)
            elif top_type == "balance":
                await self.show_balance_top(interaction, limit)
            else:
                await interaction.response.send_message('Неизвестный тип топа. Доступные: voice, messages, balance', ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f'Ошибка при получении топа: {e}', ephemeral=True)

