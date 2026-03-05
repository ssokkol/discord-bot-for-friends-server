import aiohttp
import logging
import time
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class TwitchService:
    """Service for Twitch API integration"""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self.enabled = bool(client_id and client_secret)

    async def _ensure_token(self):
        """Get or refresh OAuth2 token"""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://id.twitch.tv/oauth2/token',
                    data={
                        'client_id': self.client_id,
                        'client_secret': self.client_secret,
                        'grant_type': 'client_credentials'
                    }
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._access_token = data['access_token']
                        self._token_expires_at = time.time() + data.get('expires_in', 3600)
                    else:
                        logger.error(f"Twitch OAuth failed: {resp.status}")
        except Exception as e:
            logger.error(f"Twitch token error: {e}")

    def _headers(self) -> dict:
        return {
            'Client-ID': self.client_id,
            'Authorization': f'Bearer {self._access_token}'
        }

    async def validate_user(self, username: str) -> Optional[Dict]:
        """Validate a Twitch username and return user data"""
        if not self.enabled:
            return None

        await self._ensure_token()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'https://api.twitch.tv/helix/users?login={username}',
                    headers=self._headers()
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        users = data.get('data', [])
                        return users[0] if users else None
        except Exception as e:
            logger.error(f"Twitch validate user error: {e}")
        return None

    async def check_streams(self, usernames: List[str]) -> List[Dict]:
        """Check which of the given usernames are currently live"""
        if not self.enabled or not usernames:
            return []

        await self._ensure_token()
        results = []

        # Twitch API allows up to 100 user_logins per request
        for i in range(0, len(usernames), 100):
            batch = usernames[i:i+100]
            params = '&'.join(f'user_login={u}' for u in batch)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f'https://api.twitch.tv/helix/streams?{params}',
                        headers=self._headers()
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            results.extend(data.get('data', []))
            except Exception as e:
                logger.error(f"Twitch check streams error: {e}")

        return results

    async def check_drops(self, game_ids: List[str]) -> List[Dict]:
        """Check active drops campaigns for given game IDs"""
        if not self.enabled or not game_ids:
            return []

        await self._ensure_token()
        results = []

        for game_id in game_ids:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f'https://api.twitch.tv/helix/drops/campaigns?game_id={game_id}&status=ACTIVE',
                        headers=self._headers()
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            results.extend(data.get('data', []))
            except Exception as e:
                logger.error(f"Twitch check drops error: {e}")

        return results
