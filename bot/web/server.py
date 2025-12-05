"""
Webhook server для Render
"""
import asyncio
import httpx
from aiohttp import web
from telegram import Update

from ..config import logger, TELEGRAM_TOKEN, WEBHOOK_URL, BOT_VERSION


async def health_check(request: web.Request) -> web.Response:
    """
    Health check endpoint для Render
    
    Args:
        request: HTTP запрос
    
    Returns:
        HTTP ответ
    """
    return web.Response(
        text=f"✅ Bot {BOT_VERSION} is running",
        status=200
    )


async def telegram_webhook_handler(request: web.Request, application) -> web.Response:
    """
    Обработчик webhook от Telegram
    
    Args:
        request: HTTP запрос от Telegram
        application: Уже инициализированное приложение Telegram бота
    
    Returns:
        HTTP ответ
    """
    try:
        # Получаем данные из запроса
        data = await request.json()
        
        # Создаём объект Update из данных
        update = Update.de_json(data, application.bot)
        
        # Обрабатываем обновление через инициализированное приложение
        await application.process_update(update)
        
        return web.Response(text="OK", status=200)
    
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        return web.Response(text="Error", status=500)


async def setup_web_server(application, port: int, webhook_url: str):
    """
    Настройка и запуск web сервера для Render
    
    Args:
        application: Приложение Telegram бота (уже инициализированное)
        port: Порт для сервера
        webhook_url: URL для webhook
    """
    # Устанавливаем webhook в Telegram
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
    
    # Создаём aiohttp приложение
    app = web.Application()
    
    # Создаём замыкание для передачи application в обработчик
    async def handler(request):
        return await telegram_webhook_handler(request, application)
    
    # Добавляем роуты
    app.add_routes([
        web.post("/", handler),
        web.get("/health", health_check),
        web.get("/", health_check)  # Корневой путь тоже health check
    ])
    
    # Запускаем сервер
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"{BOT_VERSION} - 🚀 AIOHTTP Server запущен на порту {port}")
    logger.info(f"{BOT_VERSION} - ✅ Бот готов к работе!")
    
    # Бесконечный цикл для работы сервера
    await asyncio.Future()
