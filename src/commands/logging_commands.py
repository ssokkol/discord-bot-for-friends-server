import discord
import logging
from .base_command import BaseCommand

logger = logging.getLogger(__name__)


class LoggingCommands(BaseCommand):
    """Logging configuration commands"""

    def __init__(self, bot):
        super().__init__(bot)

    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the logging channel"""
        if not self.is_admin(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        await self.bot.settings_db.set('log_channel_id', str(channel.id))
        await interaction.response.send_message(f'Канал логов: {channel.mention}', ephemeral=True)
