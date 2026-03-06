import discord
from discord.ext import commands
import os
import logging
from .base_command import BaseCommand
from ..database import UserDatabase
from ..image_generator import ProfileImageGenerator
from ..utils import format_time
from ..services.level_service import LevelService

# Настройка логирования
logger = logging.getLogger(__name__)

class ProfileCommands(BaseCommand):
    """Класс для команд профиля"""

    def __init__(self, bot: commands.Bot, user_db: UserDatabase):
        super().__init__(bot)
        self.user_db = user_db
        self.image_generator = ProfileImageGenerator()

    def truncate_text(self, text: str, max_length: int) -> str:
        """Обрезает текст до максимальной длины"""
        if len(text) > max_length:
            return text[:max_length-3] + "..."
        return text

    async def show_profile(self, interaction: discord.Interaction, user: discord.Member) -> None:
        """Показывает профиль пользователя"""
        await interaction.response.defer(ephemeral=False)
        try:
            # Получаем данные пользователя
            messages = await self.user_db.get_messages(user.id)
            voice_time = await self.user_db.get_voice_time(user.id)

            # Level data
            xp, level = await self.bot.level_db.get_xp_level(user.id)
            xp_needed = LevelService.xp_for_level(level)

            # Форматируем данные
            messages_formatted = str(messages)
            messages_formatted = self.truncate_text(messages_formatted, 14)

            voice_time_formatted = format_time(voice_time)
            voice_time_formatted = self.truncate_text(voice_time_formatted, 17)

            # Даты
            created_date = user.created_at.strftime("%d.%m.%Y")
            joined_date = user.joined_at.strftime("%d.%m.%Y") if user.joined_at else "Неизвестно"

            # Ник
            nickname = self.truncate_text(str(user.name), 12)
            member = interaction.guild.get_member(user.id)

            # Подготавливаем данные для генерации изображения
            user_data = {
                'status': str(member.status),
                'avatar_url': str(user.avatar.url) if user.avatar else None,
                'nickname': nickname,
                'created_date': created_date,
                'joined_date': joined_date,
                'level': level,
                'messages': messages_formatted,
                'voice_time': voice_time_formatted,
                'xp': xp,
                'xp_needed': xp_needed,
            }

            # Генерируем изображение профиля
            output_path = f'output_{user.id}.png'
            success = await self.image_generator.generate_profile_image(user_data, output_path)

            if not success:
                await interaction.response.send_message('Ошибка генерации изображения профиля', ephemeral=True)
                return

            # Добавляем значки
            await self.image_generator.add_badges_to_profile(output_path, [str(role.id) for role in user.roles])

            # Отправляем файл
            if os.path.exists(output_path):
                file = discord.File(output_path)
                await interaction.followup.send(file=file)

                # Удаляем временный файл
                try:
                    os.remove(output_path)
                except Exception as e:
                    logger.warning(f"Не удалось удалить временный файл: {e}")
            else:
                await interaction.followup.send('Ошибка: файл профиля не найден', ephemeral=True)

        except Exception as e:
            logger.error(f"Ошибка при получении профиля: {e}")
            await interaction.followup.send(f'Ошибка при получении профиля: {e}', ephemeral=True)
