import discord
import json
import logging
from .base_command import BaseCommand

logger = logging.getLogger(__name__)


class SuggestModal(discord.ui.Modal, title="Предложение"):
    """Modal for submitting a suggestion"""

    suggestion = discord.ui.TextInput(
        label="Ваше предложение",
        style=discord.TextStyle.paragraph,
        placeholder="Опишите ваше предложение...",
        required=True,
        max_length=2000
    )

    def __init__(self, suggest_channel: discord.TextChannel):
        super().__init__()
        self.suggest_channel = suggest_channel

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Новое предложение",
            description=self.suggestion.value,
            color=0x9802BD
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        embed.set_footer(text=f"ID: {interaction.user.id}")

        msg = await self.suggest_channel.send(embed=embed)
        await msg.add_reaction("\u2705")
        await msg.add_reaction("\u274c")

        await interaction.response.send_message("Ваше предложение отправлено!", ephemeral=True)


class SuggestView(discord.ui.View):
    """Persistent view with a button to open suggestion modal"""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Предложить", style=discord.ButtonStyle.primary, custom_id="suggest_button")
    async def suggest_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_id_str = await self.bot.settings_db.get('suggest_channel_id')
        if not channel_id_str:
            await interaction.response.send_message("Канал для предложений не настроен.", ephemeral=True)
            return

        channel = self.bot.get_channel(int(channel_id_str))
        if not channel:
            await interaction.response.send_message("Канал для предложений не найден.", ephemeral=True)
            return

        await interaction.response.send_modal(SuggestModal(channel))


class SuggestCommands(BaseCommand):
    """Suggestion system commands"""

    def __init__(self, bot):
        super().__init__(bot)
        # Register persistent view
        self.bot.add_view(SuggestView(self.bot))

    async def setup_suggest(self, interaction: discord.Interaction,
                            channel: discord.TextChannel,
                            title: str = None,
                            description: str = None):
        """Setup a suggestion message with button"""
        if not self.is_owner(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        await self.bot.settings_db.set('suggest_channel_id', str(channel.id))

        embed = discord.Embed(
            title=title or "Предложения",
            description=description or "Нажмите кнопку ниже, чтобы отправить предложение по улучшению сервера.",
            color=0x9802BD
        )

        view = SuggestView(self.bot)
        await interaction.channel.send(embed=embed, view=view)

        await interaction.followup.send(
            f'Система предложений настроена! Предложения будут отправляться в {channel.mention}',
            ephemeral=True
        )
