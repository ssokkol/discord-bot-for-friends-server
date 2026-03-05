import discord
import logging
from .base_command import BaseCommand
from ..services.level_service import LevelService

logger = logging.getLogger(__name__)


class LevelCommands(BaseCommand):
    """Level system commands"""

    def __init__(self, bot):
        super().__init__(bot)

    async def show_rank(self, interaction: discord.Interaction, user: discord.Member = None):
        """Show user's level and XP"""
        if user is None:
            user = interaction.user

        await interaction.response.defer()

        try:
            if not await self.bot.user_db.user_exists(user.id):
                await interaction.followup.send('У пользователя пока нет данных.', ephemeral=True)
                return

            xp, level = await self.bot.level_db.get_xp_level(user.id)
            xp_needed = LevelService.xp_for_level(level)
            position = await self.bot.level_db.get_rank_position(user.id)

            # Progress bar
            progress = xp / xp_needed if xp_needed > 0 else 0
            bar_length = 20
            filled = int(bar_length * progress)
            bar = '`[' + '#' * filled + '-' * (bar_length - filled) + ']`'

            embed = discord.Embed(
                title=f"Ранг - {user.display_name}",
                color=user.color if user.color != discord.Color.default() else discord.Color.blurple()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="Уровень", value=str(level), inline=True)
            embed.add_field(name="XP", value=f"{xp}/{xp_needed}", inline=True)
            embed.add_field(name="Позиция", value=f"#{position}", inline=True)
            embed.add_field(name="Прогресс", value=f"{bar} {progress:.0%}", inline=False)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error showing rank: {e}")
            await interaction.followup.send('Ошибка получения данных ранга', ephemeral=True)

    async def show_leaderboard(self, interaction: discord.Interaction, page: int = 1):
        """Show level leaderboard"""
        await interaction.response.defer()

        try:
            per_page = 10
            offset = (page - 1) * per_page
            top_data = await self.bot.top_db.get_level_top(per_page, offset)

            if not top_data:
                await interaction.followup.send('Нет данных для отображения.')
                return

            embed = discord.Embed(
                title="Топ по уровням",
                color=discord.Color.gold()
            )

            lines = []
            for i, (user_id, level, xp) in enumerate(top_data, start=offset + 1):
                xp_needed = LevelService.xp_for_level(level)
                lines.append(f"**{i}.** <@{user_id}> - Уровень **{level}** ({xp}/{xp_needed} XP)")

            embed.description = "\n".join(lines)
            embed.set_footer(text=f"Страница {page}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error showing leaderboard: {e}")
            await interaction.followup.send('Ошибка получения таблицы лидеров', ephemeral=True)
