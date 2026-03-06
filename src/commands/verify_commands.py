import discord
import json
import logging
from .base_command import BaseCommand

logger = logging.getLogger(__name__)


class VerifyCommands(BaseCommand):
    """Verification system commands"""

    def __init__(self, bot):
        super().__init__(bot)

    async def setup_verify(self, interaction: discord.Interaction, title: str, description: str,
                           color: str, image_url: str, emoji: str, role: discord.Role):
        """Setup a verification message"""
        if not self.is_owner(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            color_int = int(color.replace('#', ''), 16)
        except ValueError:
            await interaction.followup.send('Неверный цвет. Используйте HEX формат: #FF0000', ephemeral=True)
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=color_int
        )
        if image_url:
            embed.set_image(url=image_url)

        msg = await interaction.channel.send(embed=embed)
        await msg.add_reaction(emoji)

        # Save to settings
        verify_data = {
            'message_id': msg.id,
            'channel_id': interaction.channel_id,
            'emoji': emoji,
            'role_id': role.id,
            'title': title,
            'description': description,
            'color': color,
            'image_url': image_url
        }
        await self.bot.settings_db.set('verify_config', json.dumps(verify_data))

        await interaction.followup.send(
            f'Верификация настроена! ID сообщения: {msg.id}, Роль: {role.mention}',
            ephemeral=True
        )

    async def edit_verify(self, interaction: discord.Interaction, title: str = None,
                          description: str = None, color: str = None, image_url: str = None):
        """Edit existing verification message"""
        if not self.is_owner(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        raw = await self.bot.settings_db.get('verify_config')
        if not raw:
            await interaction.followup.send('Верификация не настроена. Используйте /verify_setup', ephemeral=True)
            return

        data = json.loads(raw)

        if title:
            data['title'] = title
        if description:
            data['description'] = description
        if color:
            data['color'] = color
        if image_url:
            data['image_url'] = image_url

        try:
            color_int = int(data['color'].replace('#', ''), 16)
        except ValueError:
            color_int = 0x00FF00

        channel = self.bot.get_channel(data['channel_id'])
        if channel:
            try:
                msg = await channel.fetch_message(data['message_id'])
                embed = discord.Embed(
                    title=data['title'],
                    description=data['description'],
                    color=color_int
                )
                if data.get('image_url'):
                    embed.set_image(url=data['image_url'])
                await msg.edit(embed=embed)
            except Exception as e:
                logger.error(f"Error editing verify message: {e}")

        await self.bot.settings_db.set('verify_config', json.dumps(data))
        await interaction.followup.send('Верификация обновлена!', ephemeral=True)

    async def handle_reaction(self, payload: discord.RawReactionActionEvent):
        """Handle reaction for verification"""
        if payload.user_id == self.bot.user.id:
            return

        raw = await self.bot.settings_db.get('verify_config')
        if not raw:
            return

        data = json.loads(raw)

        if payload.message_id != data.get('message_id'):
            return

        emoji_str = str(payload.emoji)
        if emoji_str != data.get('emoji'):
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member:
            return

        role = guild.get_role(data.get('role_id'))
        if not role:
            return

        try:
            if role not in member.roles:
                await member.add_roles(role, reason="Verification")
                logger.info(f"Verified {member} - assigned role {role.name}")
        except Exception as e:
            logger.error(f"Error assigning verify role: {e}")
