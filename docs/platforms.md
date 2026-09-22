# Платформы: точные условия подключения

Исследование официальных API выполнено 22 сентября 2026. Ниже указано **реализованное поведение**;
наличие unit-тестов не означает, что реальные аккаунты авторизованы. Русские сервисы не включены в интеграции.

| platform | source | Что приходит | Доступ / окно при API_MAX_PAGES=3 |
|---|---|---|---|
| youtube | UC-ID, URL канала или @handle | Публикации Atom-ленты канала, включая Shorts | По UC-ID без ключа; handle разрешается через Data API key. Окно ограничено самой лентой |
| twitch | Login / URL канала | Доступные VOD, uploads, highlights | App Client ID/Secret. До 300 видео, 100 на страницу |
| tiktok | Локальное имя подключения | Публичные видео авторизовавшегося пользователя | OAuth с video.list. До 60 видео, 20 на страницу |
| instagram | Локальное имя подключения | Отдельные видео/Reels типа VIDEO | Instagram Login, профессиональный аккаунт, instagram_business_basic. До 300 медиа, включая отфильтрованные фото |
| vimeo | Локальное имя подключения | Только public/available видео указанного user ID | API access token, достаточно public-read доступа. До 75 записей, 25 на страницу; private/unlisted/processing отфильтрованы |
| peertube | https://instance/video-channels/channel или /c/channel | Публичные опубликованные видео канала, без live | Публичный REST API конкретного instance. До 300 записей |
| rss | Конечный публичный HTTPS URL | Все записи предоставленной RSS/Atom-ленты | Внешние мосты пользователь подключает самостоятельно; их наличие/стоимость/стабильность не гарантируются |

Число страниц можно менять от 1 до 10. `/status` сообщает о достижении предела. Для фото-платформ окно
считается по медиа, а не только по видео. Задержка рассылки зависит от платформы и времени обхода.
Нет обхода приватности, scraping, CAPTCHA, пользовательских cookies и неофициальных внутренних API.

## YouTube

1. Взять реальный channel ID `UC…` или ссылку `/channel/UC…`.
2. Для `@handle` / `https://www.youtube.com/@handle` включить YouTube Data API v3 в своём Google Cloud
   проекте и положить API key в `YOUTUBE_API_KEY`.
3. `/subscribe platform:youtube source:… channel:…`. Handle разрешается один раз в стабильный ID,
   так что переименование handle не меняет подписку и не создаёт повторов существующих ID.

В реализации используется Atom, не подписка WebSub; начало live не определяется отдельно,
Shorts/длинные видео не разделяются. Не используется дорогой search endpoint.
[Официальный формат ленты](https://developers.google.com/youtube/v3/guides/push_notifications),
[channels.list / forHandle](https://developers.google.com/youtube/v3/docs/channels/list).

## Twitch

Создать приложение в [Developer Console](https://dev.twitch.tv/console), заполнить `TWITCH_CLIENT_ID`
и `TWITCH_CLIENT_SECRET`. Бот использует client_credentials; пользовательские scopes для Get Videos
не требуются. App token кешируется, перевыпускается по сроку и после HTTP 401 при следующей попытке.
Сроки хранения VOD и настройки автора определяют наличие роликов. Clips и live-start — отдельные события,
в этой версии не реализованы.
[Get Videos](https://dev.twitch.tv/docs/api/videos),
[OAuth](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/).

## Авторизованные подключения

`accounts.json` — локальный JSON-объект: имя подключения → параметры. Взять структуру из `accounts.example.json`.
Удалить неиспользуемые записи. В поле `token_env` записать имя переменной; **не сам токен**. Значение этой
переменной разместить в `.env`. Для нескольких аккаунтов использовать разные aliases и переменные.
Изменения JSON перечитываются при запросах, окружение и токены из `.env` — после перезапуска.

Дополнительно можно указать `expires_at`: реальный срок токена как Unix timestamp в секундах. После него
запрос блокируется с ошибкой до обновления credentials. Если поле не задано, истечение обнаруживается
по отказу API. Файл и ответы команд не должны содержать токен. Смена владельца подключения под прежним
alias требует удаления и создания подписки с новым baseline.

### TikTok

Нужно зарегистрированное приложение с Login Kit/Display API, разрешённым `video.list` и согласие владельца
аккаунта. Пройти предусмотренный TikTok OAuth flow и получить access token. Бот не реализует callback-сайт
и не обходит проверку приложения. Указать token через `TIKTOK_CREATOR_TOKEN` (или своё имя переменной).
В Discord вводится `source:my_tiktok`, **не @username**: API выдаёт видео того пользователя, чей token передан.

TikTok выдаёт пользовательские токены с ограниченным сроком; администратор продлевает их официальным OAuth
механизмом и обновляет окружение. Автоматическое хранение/вращение refresh token в этой версии отсутствует.
[Display API / List Videos](https://developers.tiktok.com/doc/tiktok-api-v2-video-list/),
[Video Object](https://developers.tiktok.com/doc/tiktok-api-v2-video-object/),
[User access-token management](https://developers.tiktok.com/doc/oauth-user-access-token-management/).

### Instagram / Reels

Используется **Instagram API with Instagram Login**, не удалённый Basic Display API.
Нужен профессиональный аккаунт (Business/Creator), приложение Meta, его разрешения и access token со scope
`instagram_business_basic`. В `accounts.json` вписать реальный numeric `user_id` и `api_version`, поддерживаемую
вашим приложением (значение намеренно не подставлено). Развёртывание для чужих аккаунтов может требовать
проверки приложения Meta. Привязка Facebook Page для выбранного Instagram Login flow не требуется.

Бот читает `/{user_id}/media`, пропускает IMAGE/CAROUSEL_ALBUM, передаёт VIDEO/Reels со ссылкой permalink.
Stories и видео внутри карусели не включены. Произвольные личные аккаунты по нику не поддерживаются.
Пользовательский токен продлевает администратор; автоматического OAuth refresh нет.
[Meta: Instagram Login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login),
[официальная коллекция Meta и scopes](https://www.postman.com/meta/instagram/folder/6raa77c/instagram-api-with-instagram-login).
Часть страниц Meta не удалось прочитать в средстве веб-просмотра; настройки и scopes сверены с официальной
коллекцией Meta. Реальный Graph API запрос без авторизованного аккаунта не проверен.

### Vimeo

Создать приложение и read/public token, указать numeric `user_id` автора и `token_env`.
В запросах не нужны upload/delete/private permissions. Даже если token имеет private scope,
адаптер исключает private/unlisted и ещё не готовые видео. Авторизация не передаётся на URL из ответа API:
страницы запрашиваются только с api.vimeo.com.
[Создание токена](https://help.vimeo.com/hc/en-us/articles/12427789081745-How-to-generate-a-personal-access-token),
[официальная OpenAPI-схема](https://github.com/vimeo/openapi/blob/master/api.yaml).

## PeerTube и RSS

PeerTube: указать действительный HTTPS URL канала. Используется
`/api/v1/video-channels/{channelHandle}/videos`, сортировка `-publishedAt`, offset pagination, без токенов.
Для федеративного канала на другом instance используется полный `name@host`. Доступ зависит от версии и правил instance. Локальные сетевые адреса и нестандартные порты отключены.
[Официальная REST API reference](https://docs.joinpeertube.org/api-rest-reference.html#operation/getVideoChannelVideos).

RSS: использовать конечный HTTPS URL без redirects. Бот не создаёт ленту из URL страницы автора.
Не объявляется встроенная поддержка платформы лишь потому, что для неё может существовать сторонний мост.
Для лент без достоверной даты публикации работает дедупликация ID, но нельзя надёжно отличить новый ролик
от старого, который впервые появился в окне ленты.
