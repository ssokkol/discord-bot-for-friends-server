from discord import app_commands, Interaction
import discord


class GlobalCommands(app_commands.Group):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = bot.config

    @app_commands.command(name="ping", description="Проверить задержку бота")
    async def ping(self, interaction: Interaction):
        """Простая команда для проверки задержки бота"""
        await interaction.response.send_message(
            f"Понг!\nЗадержка бота: {round(self.bot.latency * 1000)}мс",
            ephemeral=True
        )

    @app_commands.command(name="help", description="Показать список доступных команд")
    async def help(self, interaction: Interaction):
        """Показывает список доступных команд в зависимости от роли пользователя"""
        from .admin_commands import AdminCommands
        admin_handler = AdminCommands(self.bot, self.bot.user_db)

        embed = discord.Embed(
            title="Список команд",
            color=0x00ff00
        )

        embed.add_field(
            name="Общие команды",
            value="* `/help` - Показать список команд\n"
                  "* `/ping` - Проверить задержку бота\n"
                  "* `/profile` - Посмотреть профиль\n"
                  "* `/rank` - Уровень и XP",
            inline=False
        )

        embed.add_field(
            name="Топ участников",
            value="* `/voice` - Топ по времени в войсе\n"
                  "* `/messages` - Топ по сообщениям\n"
                  "* `/level` - Топ по уровням\n"
                  "* `/leaderboard` - Топ по уровням",
            inline=False
        )

        embed.add_field(
            name="Музыка",
            value="* `/play` - Воспроизвести трек\n"
                  "* `/skip` - Пропустить трек\n"
                  "* `/queue` - Очередь воспроизведения\n"
                  "* `/stop` - Остановить\n"
                  "* `/pause` - Пауза/возобновление\n"
                  "* `/loop` - Повтор\n"
                  "* `/clear` - Очистить очередь",
            inline=False
        )

        role_level = admin_handler.get_role_level(interaction.user)
        is_owner = interaction.user.id == int(self.config.ADMIN_USER_ID)

        if role_level <= 1:
            admin_commands = [
                "* `/ban` - Забанить пользователя",
                "* `/kick` - Кикнуть пользователя",
                "* `/mute` - Замьютить пользователя",
            ]
            if is_owner:
                admin_commands.extend([
                    "* `/send_rules` - Отправить правила сервера",
                    "* `/verify_setup` - Настроить верификацию",
                    "* `/verify_edit` - Редактировать верификацию",
                    "* `/suggest_setup` - Настроить систему предложений",
                    "* `/logs` - Канал для логов",
                ])
            embed.add_field(
                name="Команды администратора",
                value="\n".join(admin_commands),
                inline=False
            )

            if is_owner:
                twitch_commands = [
                    "* `/twitch_add` - Добавить стримера",
                    "* `/twitch_remove` - Удалить стримера",
                    "* `/twitch_list` - Список стримеров",
                    "* `/twitch_channel` - Канал для уведомлений",
                    "* `/twitch_pingrole` - Роль для пинга",
                    "* `/drops_add` - Добавить игру для дропсов",
                    "* `/drops_remove` - Убрать игру из дропсов",
                    "* `/drops_channel` - Канал для дропсов",
                ]
                embed.add_field(
                    name="Twitch",
                    value="\n".join(twitch_commands),
                    inline=False
                )

        elif role_level <= 3:
            embed.add_field(
                name="Команды модератора",
                value="* `/kick` - Кикнуть пользователя\n"
                      "* `/mute` - Замьютить пользователя",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)
