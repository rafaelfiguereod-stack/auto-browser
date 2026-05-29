import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.browser.services.bot_challenge import BrowserBotChallengeService


class BotChallengeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_detects_bot_challenge_from_page_text(self) -> None:
        page = SimpleNamespace(
            url="https://example.com/login",
            title=AsyncMock(return_value="Security Check"),
            evaluate=AsyncMock(
                side_effect=[
                    "Please verify you are human before continuing",
                    ["https://challenge.cloudflare.com/frame"],
                ]
            ),
        )
        session = SimpleNamespace(page=page)

        result = await BrowserBotChallengeService().check(session)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result["bot_challenge_detected"])
        self.assertEqual(result["url"], "https://example.com/login")

    async def test_returns_none_for_normal_page(self) -> None:
        page = SimpleNamespace(
            url="https://example.com/dashboard",
            title=AsyncMock(return_value="Dashboard"),
            evaluate=AsyncMock(side_effect=["Welcome back", []]),
        )
        session = SimpleNamespace(page=page)

        self.assertIsNone(await BrowserBotChallengeService().check(session))
