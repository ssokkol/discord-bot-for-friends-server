import discord
import random
import logging
from datetime import timedelta
from .base_command import BaseCommand

logger = logging.getLogger(__name__)


class DailyCommands(BaseCommand):
    """Daily bonus commands"""

    def __init__(self, bot):
        super().__init__(bot)

    async def claim_daily(self, interaction: discord.Interaction):
        """Claim daily bonus"""
        await interaction.response.defer()

        try:
            user_id = interaction.user.id

            if not await self.bot.user_db.user_exists(user_id):
                await self.bot.user_db.add_user(user_id)

            last_daily_str, streak = await self.bot.level_db.get_daily_info(user_id)

            now = discord.utils.utcnow()
            today_str = now.strftime('%Y-%m-%d')

            # Check if already claimed today
            if last_daily_str == today_str:
                await interaction.followup.send('Вы уже забрали ежедневный бонус сегодня!', ephemeral=True)
                return

            # Check streak
            if last_daily_str:
                from datetime import datetime
                last_date = datetime.strptime(last_daily_str, '%Y-%m-%d').date()
                yesterday = (now - timedelta(days=1)).date()
                if last_date == yesterday:
                    streak += 1
                    if streak > 7:
                        streak = 1
                else:
                    streak = 1
            else:
                streak = 1

            # Calculate reward
            config = self.bot.config
            base_reward = random.randint(config.DAILY_MIN, config.DAILY_MAX)

            # Streak bonus
            streak_bonus = 0
            if streak >= 2:
                streak_bonus = min((streak - 1) * 50, 300)

            total_reward = base_reward + streak_bonus

            # Apply reward
            await self.bot.user_db.add_money(user_id, total_reward)
            await self.bot.level_db.set_daily_info(user_id, today_str, streak)

            # Log transaction
            new_balance = await self.bot.user_db.get_money(user_id)
            await self.bot.transaction_db.log(user_id, 'daily', total_reward, new_balance,
                                              f'streak:{streak}')

            # Build embed
            embed = discord.Embed(
                title="Ежедневный бонус!",
                color=discord.Color.gold()
            )

            desc_parts = [f"Базовая награда: **{base_reward}** монет"]
            if streak_bonus > 0:
                desc_parts.append(f"Бонус за серию (день {streak}): **+{streak_bonus}** монет")
            desc_parts.append(f"\nИтого: **{total_reward}** монет")
            desc_parts.append(f"Баланс: **{new_balance}** монет")

            embed.description = "\n".join(desc_parts)

            # Streak indicator
            streak_bar = ""
            for i in range(1, 8):
                if i <= streak:
                    streak_bar += "**[X]** "
                else:
                    streak_bar += "[ ] "
            embed.add_field(name=f"Серия: {streak}/7", value=streak_bar, inline=False)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error claiming daily: {e}")
            await interaction.followup.send('Ошибка при получении ежедневного бонуса', ephemeral=True)
