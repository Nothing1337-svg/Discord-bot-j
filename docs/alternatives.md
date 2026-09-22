# Похожие боты и границы поддержки

Проверено 22 сентября 2026. Сравнение основано на официальных сайтах; тарифы и задержки не проверялись.

| Решение | Назначение | Отличие этого проекта |
|---|---|---|
| [MonitoRSS](https://docs.monitorss.xyz/) | RSS в Discord, панель управления | Здесь управление slash-командами, своя SQLite и баннер |
| [Pingcord](https://pingcord.xyz/) | Уведомления нескольких платформ, включая YouTube, Twitch, TikTok | Здесь самостоятельный хостинг и открытый исходный код; меньше встроенных платформ |
| [Noti](https://noti.bot/) | Уведомления Twitch, Kick, YouTube, Rumble, TikTok и других | Здесь YouTube/Twitch/RSS; нет обещания универсального доступа к закрытым платформам |

## Поддержка в проекте

| Источник | Подключение | Ограничения |
|---|---|---|
| YouTube | `/subscribe platform:youtube source:UC… channel:#видео` | Реальный ID канала, не @handle. RSS выдаёт ограниченное число последних записей; Shorts/обычные видео не разделяются. События старта live отдельно не отслеживаются |
| Twitch | `/subscribe platform:twitch source:логин channel:#видео` | Нужны Client ID/Secret приложения. Последние 100 доступных видео: архивы/загрузки/хайлайты. Нет live/клипов; публикация VOD зависит от настроек автора |
| PeerTube, Vimeo, Dailymotion, Rumble и другие | `/subscribe platform:rss source:https://… channel:#видео` | Только если конкретный источник предоставляет действующую RSS/Atom-ленту. Автоопределения URL ленты нет |
| TikTok, Instagram/Reels, VK Видео, Дзен, Rutube, Kick, X и прочие | RSS/Atom от разрешённого внешнего сервиса/моста | Встроенных API-адаптеров для этих платформ нет. Пользователь предоставляет реальную доступную ленту; подписка внешнего сервиса может быть платной |

RSS-адаптер передаёт все записи ленты: используйте ленту видео, иначе будут приходить также статьи/посты.
HTTPS обязателен; перенаправления отключены. Укажите конечный публичный URL. Ленты из локальной сети не поддерживаются.
Нет scraping, обхода авторизации, поиска всех авторов или сбора приватных видео. Подписки задаются явно.

## Первичные технические источники

- [YouTube Atom feed / push notifications](https://developers.google.com/youtube/v3/guides/push_notifications) — формат и адрес Atom. Здесь используется polling, а не PubSubHubbub.
- [Twitch Videos API](https://dev.twitch.tv/docs/api/videos)
- [Twitch OAuth Client Credentials](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/)
- [Discord Guild resource](https://github.com/discord/discord-api-docs/blob/main/developers/resources/guild.mdx)
- [discord.py Intents](https://discordpy.readthedocs.io/en/stable/intents.html)
- [aiohttp client](https://docs.aiohttp.org/en/stable/client_advanced.html)
