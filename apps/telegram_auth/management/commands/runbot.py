import asyncio

from django.core.management.base import BaseCommand

from apps.telegram_auth.bot import run_bot


class Command(BaseCommand):
    help = "Telegram bot'ni long polling rejimida ishga tushiradi"

    def handle(self, *args, **options):
        asyncio.run(run_bot())
