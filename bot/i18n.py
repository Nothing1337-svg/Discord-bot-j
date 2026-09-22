TEXT = {
    "ru": {"new": "Новое видео", "voice": "СЕЙЧАС В ГОЛОСОВЫХ", "subtitle": "Общаемся. Играем. Остаёмся на связи.",
           "added": "Подписка добавлена. Текущие ролики запомнены; дальше придут только новые.",
           "removed": "Подписка удалена.", "missing": "Подписка не найдена.",
           "empty": "Подписок пока нет.", "checked": "Проверка завершена.",
           "error": "Операция не выполнена. Проверьте настройки и журнал бота.",
           "working": "Бот работает", "sources": "Подписок", "failed": "Последняя проверка с ошибкой"},
    "en": {"new": "New video", "voice": "IN VOICE RIGHT NOW", "subtitle": "Talk. Play. Stay connected.",
           "added": "Subscription added. Existing videos recorded; only new videos will be sent.",
           "removed": "Subscription removed.", "missing": "Subscription not found.",
           "empty": "No subscriptions yet.", "checked": "Check complete.",
           "error": "Operation failed. Check configuration and bot logs.",
           "working": "Bot is running", "sources": "Subscriptions", "failed": "Last check failed"},
}


def tr(language, key):
    return TEXT[language][key]
