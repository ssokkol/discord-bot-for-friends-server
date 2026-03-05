import os
from dotenv import load_dotenv


class Config:
    """Bot configuration class"""

    def __init__(self):
        load_dotenv()

        # Discord configuration
        self.DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
        self.GUILD_ID = int(os.getenv('GUILD_ID', 0))
        self.ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')
        # Admin role levels
        admin_roles = os.getenv('ADMIN_ROLES', '').split(',')
        self.ADMIN_ROLE_LVL0 = int(admin_roles[0]) if len(admin_roles) > 0 and admin_roles[0] else 0
        self.ADMIN_ROLE_LVL1 = int(admin_roles[1]) if len(admin_roles) > 1 and admin_roles[1] else 0
        self.ADMIN_ROLE_LVL2 = int(admin_roles[2]) if len(admin_roles) > 2 and admin_roles[2] else 0

        # Role hierarchy (replaces hardcoded list in admin_commands)
        role_hierarchy_str = os.getenv('ROLE_HIERARCHY', '')
        self.ROLE_HIERARCHY = [int(r) for r in role_hierarchy_str.split(',') if r.strip()]

        # Economy
        self.TRANSFER_COMMISSION_RATE = float(os.getenv('TRANSFER_COMMISSION_RATE', 0.1))
        self.INITIAL_MONEY = int(os.getenv('INITIAL_MONEY', 10))
        self.INITIAL_MESSAGES = int(os.getenv('INITIAL_MESSAGES', 1))

        # Roles
        self.BADGE_ROLES = [int(role_id) for role_id in os.getenv('BADGE_ROLES', '').split(',') if role_id]

        # Database
        self.DATABASE_PATH = os.getenv('DATABASE_PATH', 'club.db')

        # Bot activity
        self.BOT_ACTIVITY_NAME = os.getenv('BOT_ACTIVITY_NAME', 'Playing')

        # Voice rewards
        self.VOICE_TIME_REWARD = int(os.getenv('VOICE_TIME_REWARD', 1))
        self.VOICE_MONEY_REWARD = int(os.getenv('VOICE_MONEY_REWARD', 20))
        self.VOICE_CHECK_INTERVAL = int(os.getenv('VOICE_CHECK_INTERVAL', 1))

        # Dynamic voice channels
        self.DYNAMIC_VOICE_CATEGORY_ID = int(os.getenv('DYNAMIC_VOICE_CATEGORY_ID', 0))
        self.DYNAMIC_VOICE_LOBBY_ID = int(os.getenv('DYNAMIC_VOICE_LOBBY_ID', 0))

        # Spotify API
        self.SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID', '')
        self.SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET', '')

        # Music player
        self.MUSIC_INACTIVITY_TIMEOUT = int(os.getenv('MUSIC_INACTIVITY_TIMEOUT', 300))
        self.MUSIC_MAX_QUEUE_SIZE = int(os.getenv('MUSIC_MAX_QUEUE_SIZE', 100))
        self.MUSIC_DEFAULT_VOLUME = int(os.getenv('MUSIC_DEFAULT_VOLUME', 50))
        self.MUSIC_CHANNEL_ID = int(os.getenv('MUSIC_CHANNEL_ID', 0)) or None

        # Backup
        self.BACKUP_CHANNEL_ID = int(os.getenv('BACKUP_CHANNEL_ID', 0)) or None

        # Level system
        self.XP_MESSAGE_MIN = int(os.getenv('XP_MESSAGE_MIN', 15))
        self.XP_MESSAGE_MAX = int(os.getenv('XP_MESSAGE_MAX', 25))
        self.XP_MESSAGE_COOLDOWN = int(os.getenv('XP_MESSAGE_COOLDOWN', 60))
        self.XP_VOICE_PER_MINUTE = int(os.getenv('XP_VOICE_PER_MINUTE', 10))

        # Daily bonus
        self.DAILY_MIN = int(os.getenv('DAILY_MIN', 100))
        self.DAILY_MAX = int(os.getenv('DAILY_MAX', 300))

        # Games
        self.GAME_COOLDOWN = int(os.getenv('GAME_COOLDOWN', 5))
        self.GAME_MIN_BET = int(os.getenv('GAME_MIN_BET', 50))

        # Twitch
        self.TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID', '')
        self.TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET', '')
        self.TWITCH_CHECK_INTERVAL = int(os.getenv('TWITCH_CHECK_INTERVAL', 3))

    def validate(self):
        """Validates required configuration fields. Raises ValueError on missing."""
        errors = []
        if not self.DISCORD_TOKEN:
            errors.append('DISCORD_TOKEN is required')
        if not self.GUILD_ID:
            errors.append('GUILD_ID is required')
        if not self.ADMIN_USER_ID:
            errors.append('ADMIN_USER_ID is required')
        if errors:
            raise ValueError('Configuration errors: ' + '; '.join(errors))
