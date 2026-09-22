TEXT = {
    "ru": {"new": "Новое видео", "voice": "СЕЙЧАС В ГОЛОСОВЫХ", "subtitle": "Общаемся. Играем. Остаёмся на связи.",
           "added": "Подписка добавлена. Текущие ролики запомнены; дальше придут только новые.",
           "removed": "Подписка удалена.", "missing": "Подписка не найдена.",
           "empty": "Подписок пока нет.", "checked": "Проверка завершена.",
           "error": "Операция не выполнена. Проверьте настройки и журнал бота.",
           "working": "Проверка источников работает", "sources": "Подписок", "failed": "Подписок с ошибкой",
           "checking": "Проверка запрошена. Результат и очередь доступны в /status.",
           "pending": "Ссылок в очереди", "window": "Достигнут лимит страниц API (ограниченное окно)",
           "stopped": "Проверка источников остановлена — проверьте журнал и перезапустите бота",
           "platform_help": "YouTube: UC-ID / @handle (для handle нужен API key). Twitch: логин. "
                            "PeerTube: URL канала. RSS: URL ленты. TikTok, Instagram, Vimeo: "
                            "настроенный локально alias из accounts.json. Токены в Discord не вводите. "
                            "Инструкция: https://github.com/Nothing1337-svg/Discord-bot-j/blob/main/docs/platforms.md"},
    "en": {"new": "New video", "voice": "IN VOICE RIGHT NOW", "subtitle": "Talk. Play. Stay connected.",
           "added": "Subscription added. Existing videos recorded; only new videos will be sent.",
           "removed": "Subscription removed.", "missing": "Subscription not found.",
           "empty": "No subscriptions yet.", "checked": "Check complete.",
           "error": "Operation failed. Check configuration and bot logs.",
           "working": "Polling is running", "sources": "Subscriptions", "failed": "Subscriptions with errors",
           "checking": "Check requested. See /status for results and pending deliveries.",
           "pending": "Pending links", "window": "API page limit reached (bounded history)",
           "stopped": "Polling stopped — check logs and restart the bot",
           "platform_help": "YouTube: UC-ID / @handle (API key required for handles). Twitch: login. "
                            "PeerTube: channel URL. RSS: feed URL. TikTok, Instagram, Vimeo: "
                            "local accounts.json alias. Never enter tokens in Discord. "
                            "Setup: https://github.com/Nothing1337-svg/Discord-bot-j/blob/main/docs/platforms.md"},
}


def tr(language, key):
    return TEXT[language][key]
