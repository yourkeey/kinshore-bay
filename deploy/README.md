# Private VPS preview

The Compose project runs Django with Gunicorn and SQLite. It listens on the VPS loopback interface at port 8876. Keep this HTTP configuration behind an SSH tunnel. The local Django preview keeps its own database and settings.

The VPS keeps each Git archive under `~/kinshore-bay/releases/<commit>`. From a release directory, create the shared environment file once and preserve it between releases.

```sh
umask 077
test -s ../../preview.env || python3 -c 'from secrets import token_urlsafe; print("KINSHORE_SECRET_KEY=" + token_urlsafe(64))' > ../../preview.env
docker compose --env-file ../../preview.env -f deploy/compose.yaml up -d --build --wait
docker compose --env-file ../../preview.env -f deploy/compose.yaml exec web python manage.py create_reception_user receptionist
```

Open the tunnel from your workstation. Substitute the address, user and key authorized for the VPS.

```sh
ssh -N -L 127.0.0.1:8876:127.0.0.1:8876 -i /path/to/key user@server
```

Open [Guest site](http://127.0.0.1:8876/site/index.html) and [Reception](http://127.0.0.1:8876/reception/) in separate profiles. To refresh the test shift, run `docker compose --env-file ../../preview.env -f deploy/compose.yaml exec web python manage.py seed_demo --shift`.

Use `docker compose --env-file ../../preview.env -f deploy/compose.yaml ps` to inspect health and `docker compose --env-file ../../preview.env -f deploy/compose.yaml logs --tail=50 web` for startup errors. `docker compose --env-file ../../preview.env -f deploy/compose.yaml stop web` stops this preview and retains its data. The named volume `kinshore-bay_data` contains only VPS demo records.

## Telegram bot

Prepare `~/kinshore-bay/bot.env` with `BOT_TOKEN` and file permissions `0600`. The shared `preview.env` also needs `KINSHORE_CRM_USER` and a random `KINSHORE_CRM_TOKEN`. Keep these files outside every release archive.

From the release directory, use the Telegram overlay for updates to both services:

```sh
compose() {
    docker compose --env-file ../../preview.env -f deploy/compose.yaml -f deploy/telegram.compose.yaml "$@"
}
compose up -d --build --wait web
compose exec -T web python manage.py setup_bot_service
compose up -d --build --wait
compose logs --tail=30 bot
```

The bot uses Telegram long polling. Keep a single running instance for the token. The bot reaches the CRM on the web container's loopback and publishes no port of its own. The `kinshore-bay_bot-drafts` volume preserves selected demo requests for `/resume`. Once the log reports `Telegram long polling connected.`, open the bot in Telegram and send `/start`.

### Open the public Mini App from Telegram

The live [Kinshore Bay bot](https://t.me/KinshoreBay_app) uses [the public planner](https://kinshore-bay.scalo.biz/site/miniapp.html).

Deploy the [public demo](PUBLIC-DEMO.md) first. Verify that its `/site/miniapp.html` opens over HTTPS and returns the planner from outside the VPS. Add or replace `MINI_APP_URL=https://your-hostname/site/miniapp.html` in the existing `~/kinshore-bay/bot.env`. Preserve the rest of the file and its permissions.

From the active private release, use the `compose` function above to recreate just the bot and load the updated environment.

```sh
compose up -d --no-deps --force-recreate bot
compose logs --tail=30 bot
```

The permanent chat menu is a separate Telegram setting. Set its **Open Mini App** button to the same URL via BotFather or `setChatMenuButton`. Confirm it with `getChatMenuButton` when changing hosts. To remove both entry points, reset the Telegram menu to commands and remove `MINI_APP_URL` before recreating the bot. [Telegram menu button](https://core.telegram.org/bots/webapps#launching-mini-apps-from-the-menu-button)

Send `/start` in a private chat in the Telegram mobile app and tap **Open Mini App**. Check that the planner loads, returns a quote and shows a submitted request in **My stay**. Close and reopen the app to check session persistence. The planner uses its public demo workspace, while bot chat requests use the private preview CRM.

A public release needs its own HTTPS configuration, host allowlist and production database settings.
