# Public Kinshore Bay demo

Run this stack in its own directory on a Docker Compose host. It creates a separate PostgreSQL database for fictional records. The private preview and its Telegram bot use their existing Compose project and data volumes.

## Prepare the release

From the project root, run the CRM and browser regressions before packaging. The browser command uses Playwright and an isolated test database. [Browser setup](../site/README.md)

```powershell
& 'crm/.venv/Scripts/python.exe' crm/manage.py test reception
if ($LASTEXITCODE -ne 0) { throw 'CRM regression failed' }
& 'crm/.venv/Scripts/python.exe' site/check_guest_route.py
if ($LASTEXITCODE -ne 0) { throw 'Browser regression failed' }
python deploy/package_public.py kinshore-public-demo.zip
```

The archive contains the public runtime and the referenced site images. Extract it into a clean release directory on the host with a `022` umask so the non-root container user can read the packaged directories.

```sh
(umask 022; unzip /path/to/kinshore-public-demo.zip)
```

## Publish

1. Point the demo hostname to the server and verify that TCP ports 80 and 443 are available. Publish an AAAA record only if the server is reachable on IPv6. Caddy obtains and renews the HTTPS certificate. [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https)
2. Create a public environment file outside the release directory and limit it to its owner. Set `KINSHORE_DEMO_HOST` to the hostname alone. Generate independent random values for `KINSHORE_SECRET_KEY` and `KINSHORE_POSTGRES_PASSWORD`.
3. Extract the release into a new directory and validate the configuration before starting it.

```sh
docker compose --env-file ../public.env -f deploy/public.compose.yaml config --quiet
docker compose --env-file ../public.env -f deploy/public.compose.yaml up -d --build --wait
docker compose --env-file ../public.env -f deploy/public.compose.yaml ps
```

### Use an upstream HTTPS proxy

When another server terminates HTTPS, set `KINSHORE_UPSTREAM_IP` in the public environment file to the VPS address reachable from that proxy over the private network. Use the proxy overlay to publish HTTP on that address at port `8876`.

```sh
docker compose --env-file ../public.env -f deploy/public.compose.yaml -f deploy/public.proxy.compose.yaml config --quiet
docker compose --env-file ../public.env -f deploy/public.compose.yaml -f deploy/public.proxy.compose.yaml up -d --build --wait web
```

Configure the upstream proxy to connect to `http://<KINSHORE_UPSTREAM_IP>:8876`, preserve the public hostname in `Host`, and overwrite `X-Forwarded-Proto` with `https` for HTTPS requests. Redirect public HTTP to HTTPS at the proxy. The root URL opened by IP returns an HTTP 200 status message over the private network. To check the application itself, send the same headers as the proxy.

```sh
curl --fail --header 'Host: your-public-hostname' --header 'X-Forwarded-Proto: https' \
  http://<KINSHORE_UPSTREAM_IP>:8876/content/en.json
```

### Verify and maintain the demo

Open the HTTPS home page and send a guest request. Use **Open demo reception** to confirm it. In a second private profile, check that the first reference is absent from **Today** and cannot be opened by URL. In the first profile, select **Guest My stay** and book a walk. Verify the HTTP to HTTPS redirect and the mobile route on a phone before sharing the link.

With Playwright and Chromium available, run the guest and Reception regression against the deployed demo. The test creates fictional stays in separate demo workspaces. [Browser setup](../site/README.md)

```powershell
$env:KINSHORE_TEST_URL = 'https://kinshore-bay.scalo.biz'
$env:KINSHORE_TEST_PUBLIC = '1'
python site/test_guest_route.py
```

A visitor's workspace expires after 24 hours. Schedule the following command daily on the host, using absolute paths for the environment file and the active release. It runs at web startup as well.

```sh
docker compose --env-file /path/to/public.env -f /path/to/release/deploy/public.compose.yaml \
  exec -T web python manage.py clear_public_demo
```

In direct HTTPS mode, stop `edge` to pause public traffic. With the proxy overlay, stop `web` using both Compose files. The database and certificate volumes persist across releases.
