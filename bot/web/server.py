"""
Webhook server для Render (исправленная версия)
"""
import asyncio
import httpx
from aiohttp import web
from telegram import Update

from ..config import logger, TELEGRAM_TOKEN, WEBHOOK_URL, BOT_VERSION


async def health_check(request: web.Request) -> web.Response:
    return web.Response(
        text=f"✅ Bot {BOT_VERSION} is running",
        status=200
    )


async def telegram_webhook_handler(request: web.Request, application) -> web.Response:
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return web.Response(text="OK", status=200)
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        return web.Response(text="Error", status=500)


async def setup_web_server(application, port: int, webhook_url: str):
    # ✅ Инициализируем и запускаем application ДО установки webhook
    await application.initialize()
    await application.start()

    # Устанавливаем webhook
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
            json={"url": f"{webhook_url}/"}
        )
        if response.status_code == 200 and response.json().get('ok'):
            logger.info(f"{BOT_VERSION} - ✅ Webhook успешно установлен: {webhook_url}/")
        else:
            logger.error(f"{BOT_VERSION} - ❌ Ошибка установки Webhook: {response.text}")
            return

    # Запускаем AIOHTTP сервер
    app = web.Application()
    async def handler(request):
        return await telegram_webhook_handler(request, application)
    
    app.add_routes([
        web.post("/", handler),
        web.get("/health", health_check),
        web.get("/", health_check)
    ])
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"{BOT_VERSION} - 🚀 AIOHTTP Server запущен на порту {port}")
    logger.info(f"{BOT_VERSION} - ✅ Бот готов к работе!")
    
    await asyncio.Future()  # бесконечный цикл
