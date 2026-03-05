import time
import random
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class LevelService:
    """Service for XP/level management"""

    def __init__(self, bot):
        self.bot = bot
        self._xp_cooldowns: dict[int, float] = {}  # user_id -> last_xp_time

    @staticmethod
    def xp_for_level(level: int) -> int:
        """XP needed to reach the next level from current level"""
        return 5 * (level ** 2) + 50 * level + 100

    @staticmethod
    def total_xp_for_level(level: int) -> int:
        """Total XP needed to reach a given level from 0"""
        total = 0
        for lvl in range(level):
            total += 5 * (lvl ** 2) + 50 * lvl + 100
        return total

    def is_on_cooldown(self, user_id: int) -> bool:
        """Check if user is on XP cooldown for messages"""
        now = time.time()
        last = self._xp_cooldowns.get(user_id, 0)
        return (now - last) < self.bot.config.XP_MESSAGE_COOLDOWN

    def set_cooldown(self, user_id: int):
        """Set XP cooldown for user"""
        self._xp_cooldowns[user_id] = time.time()

    async def add_xp(self, user_id: int, amount: int) -> Tuple[int, bool]:
        """
        Add XP to user and check for level up.
        Returns (new_level, leveled_up)
        """
        level_db = self.bot.level_db
        current_xp, current_level = await level_db.get_xp_level(user_id)

        new_xp = current_xp + amount
        new_level = current_level
        leveled_up = False

        # Check for level ups
        while new_xp >= self.xp_for_level(new_level):
            new_xp -= self.xp_for_level(new_level)
            new_level += 1
            leveled_up = True

        await level_db.set_xp_level(user_id, new_xp, new_level)

        return new_level, leveled_up

    async def add_message_xp(self, user_id: int) -> Optional[Tuple[int, bool]]:
        """Add random message XP if not on cooldown. Returns (level, leveled_up) or None."""
        if self.is_on_cooldown(user_id):
            return None

        self.set_cooldown(user_id)
        amount = random.randint(self.bot.config.XP_MESSAGE_MIN, self.bot.config.XP_MESSAGE_MAX)
        return await self.add_xp(user_id, amount)

    async def add_voice_xp(self, user_id: int) -> Tuple[int, bool]:
        """Add voice XP (called every minute)"""
        return await self.add_xp(user_id, self.bot.config.XP_VOICE_PER_MINUTE)

    async def get_rank_position(self, user_id: int) -> int:
        """Get user's rank position on the server"""
        return await self.bot.level_db.get_rank_position(user_id)

    async def check_level_roles(self, member, new_level: int):
        """Assign roles based on level milestones"""
        try:
            level_roles = await self.bot.level_db.get_level_roles()
            guild = member.guild

            for level, role_id in level_roles:
                role = guild.get_role(role_id)
                if not role:
                    continue
                if new_level >= level and role not in member.roles:
                    await member.add_roles(role, reason=f"Reached level {level}")
        except Exception as e:
            logger.error(f"Error assigning level roles: {e}")
