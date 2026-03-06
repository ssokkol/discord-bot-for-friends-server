import discord
import logging
from .base_command import BaseCommand

logger = logging.getLogger(__name__)


class TwitchCommands(BaseCommand):
    """Twitch integration commands"""

    def __init__(self, bot):
        super().__init__(bot)

    async def add_streamer(self, interaction: discord.Interaction, username: str):
        """Add a Twitch streamer to track"""
        if not self.is_owner(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Validate via API
        user_data = await self.bot.twitch_service.validate_user(username)
        if not user_data:
            await interaction.followup.send(f'Twitch пользователь `{username}` не найден.', ephemeral=True)
            return

        twitch_id = user_data.get('id')
        await self.bot.twitch_db.add_streamer(username, twitch_id, interaction.user.id)
        await interaction.followup.send(
            f'Теперь отслеживается **{user_data.get("display_name", username)}** на Twitch!',
            ephemeral=True
        )

    async def remove_streamer(self, interaction: discord.Interaction, username: str):
        """Remove a tracked streamer"""
        if not self.is_owner(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        await self.bot.twitch_db.remove_streamer(username)
        await interaction.response.send_message(f'`{username}` удален из отслеживания.', ephemeral=True)

    async def list_streamers(self, interaction: discord.Interaction):
        """List tracked streamers"""
        streamers = await self.bot.twitch_db.get_streamers()

        embed = discord.Embed(title="Отслеживаемые стримеры", color=discord.Color.purple())

        if not streamers:
            embed.description = "Нет отслеживаемых стримеров."
        else:
            lines = []
            for _, username, _, is_live, _ in streamers:
                status = "В эфире" if is_live else "Не в эфире"
                lines.append(f"**{username}** - {status}")
            embed.description = "\n".join(lines)

        await interaction.response.send_message(embed=embed)

    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the Twitch alerts channel"""
        if not self.is_owner(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        await self.bot.settings_db.set('twitch_channel_id', str(channel.id))
        await interaction.response.send_message(f'Канал Twitch уведомлений: {channel.mention}', ephemeral=True)

    async def set_ping_role(self, interaction: discord.Interaction, role: discord.Role):
        """Set the role to ping for stream alerts"""
        if not self.is_owner(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        await self.bot.settings_db.set('twitch_ping_role_id', str(role.id))
        await interaction.response.send_message(f'Роль для пинга стримов: {role.mention}', ephemeral=True)
