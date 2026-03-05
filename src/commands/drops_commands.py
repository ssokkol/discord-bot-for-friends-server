import discord
import logging
from .base_command import BaseCommand

logger = logging.getLogger(__name__)


class DropsCommands(BaseCommand):
    """Twitch Drops commands"""

    def __init__(self, bot):
        super().__init__(bot)

    async def add_game(self, interaction: discord.Interaction, game_name: str):
        """Add a game for drops tracking"""
        if not self.is_admin(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        await self.bot.twitch_db.add_drops_game(game_name, added_by=interaction.user.id)
        await interaction.response.send_message(f'Отслеживание дропсов для **{game_name}** включено!', ephemeral=True)

    async def remove_game(self, interaction: discord.Interaction, game_name: str):
        """Remove a game from drops tracking"""
        if not self.is_admin(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        await self.bot.twitch_db.remove_drops_game(game_name)
        await interaction.response.send_message(f'**{game_name}** удалена из отслеживания дропсов.', ephemeral=True)

    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the drops alert channel"""
        if not self.is_admin(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        await self.bot.settings_db.set('drops_channel_id', str(channel.id))
        await interaction.response.send_message(f'Канал дропсов: {channel.mention}', ephemeral=True)
