import discord
import logging
from .base_command import BaseCommand

logger = logging.getLogger(__name__)


class RulesCommands(BaseCommand):
    """Server rules command"""

    def __init__(self, bot):
        super().__init__(bot)

    async def send_rules(self, interaction: discord.Interaction):
        """Send server rules as a beautiful embed"""
        if not self.is_owner(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title="Правила сервера",
            description="Добро пожаловать! Пожалуйста, ознакомьтесь с правилами сервера. "
                        "Нарушение правил может привести к муту или бану.",
            color=0x9802BD
        )

        embed.add_field(
            name="1. Уважение",
            value="```Относитесь к другим участникам с уважением. "
                  "Запрещены оскорбления, травля, дискриминация и токсичное поведение.```",
            inline=False
        )

        embed.add_field(
            name="2. Спам и флуд",
            value="```Запрещён спам, флуд, чрезмерное использование капса и "
                  "бессмысленные сообщения. Используйте каналы по назначению.```",
            inline=False
        )

        embed.add_field(
            name="3. NSFW контент",
            value="```Любой контент 18+ строго запрещён во всех каналах сервера.```",
            inline=False
        )

        embed.add_field(
            name="4. Реклама",
            value="```Запрещена любая реклама без разрешения администрации. "
                  "Это включает ссылки на другие серверы, каналы и сервисы.```",
            inline=False
        )

        embed.add_field(
            name="5. Голосовые каналы",
            value="```Запрещены громкие звуки, звуковые доски (саундпады) без согласия участников, "
                  "а также намеренные помехи в голосовых каналах.```",
            inline=False
        )

        embed.add_field(
            name="6. Никнеймы и аватары",
            value="```Никнеймы и аватары не должны содержать оскорбительный, "
                  "провокационный или неприемлемый контент.```",
            inline=False
        )

        embed.add_field(
            name="7. Личная информация",
            value="```Запрещено распространение чужой личной информации (доксинг). "
                  "Берегите свою и чужую конфиденциальность.```",
            inline=False
        )

        embed.add_field(
            name="8. Читы и эксплойты",
            value="```Запрещено обсуждение и распространение читов, "
                  "эксплойтов и любого нечестного ПО для игр.```",
            inline=False
        )

        embed.add_field(
            name="9. Администрация",
            value="```Решения администрации являются окончательными. "
                  "Если вы не согласны — обратитесь в личные сообщения к админу.```",
            inline=False
        )

        embed.add_field(
            name="10. Право администрации",
            value="```Администрация оставляет за собой право наказать участника "
                  "даже при отсутствии конкретного правила, если его поведение "
                  "наносит вред серверу или его участникам.```",
            inline=False
        )

        embed.set_footer(text="Незнание правил не освобождает от ответственности")

        await interaction.channel.send(embed=embed)
        await interaction.followup.send('Правила отправлены!', ephemeral=True)
