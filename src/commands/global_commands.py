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
                  "* `/balance` - Топ по балансу\n"
                  "* `/transfer` - Перевести деньги другому пользователю\n"
                  "* `/profile` - Посмотреть профиль\n"
                  "* `/rank` - Уровень и XP\n"
                  "* `/leaderboard` - Топ по уровням\n"
                  "* `/daily` - Ежедневный бонус",
            inline=False
        )

        embed.add_field(
            name="Игры",
            value="* `/coinflip <сумма>` - Подбросить монетку (x1.8)\n"
                  "* `/dice <сумма>` - Кости (x2)\n"
                  "* `/duel @user <сумма>` - Дуэль с игроком",
            inline=False
        )

        embed.add_field(
            name="Магазин",
            value="* `/shop` - Магазин предметов\n"
                  "* `/buy <id>` - Купить предмет\n"
                  "* `/inventory` - Инвентарь\n"
                  "* `/equip <id>` - Экипировать предмет",
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

        if role_level <= 1:
            admin_commands = [
                "* `/ban` - Забанить пользователя",
                "* `/kick` - Кикнуть пользователя",
                "* `/mute` - Замьютить пользователя",
            ]
            if interaction.user.id == int(self.config.ADMIN_USER_ID):
                admin_commands.extend([
                    "* `/give` - Выдать деньги пользователю",
                    "* `/rem` - Снять деньги у пользователя",
                    "* `/economy_reset` - Сбросить баланс",
                    "* `/shop_add` - Добавить предмет в магазин",
                    "* `/shop_remove` - Удалить предмет из магазина",
                    "* `/twitch add/remove/list` - Twitch стримеры",
                    "* `/logs channel` - Канал для логов",
                    "* `/verify setup` - Настроить верификацию",
                ])
            embed.add_field(
                name="Команды администратора",
                value="\n".join(admin_commands),
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
