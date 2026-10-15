# Run Aveon on the default HTTP port (80) via IIS reverse proxy

Remote face readers reach the server on the **default port 80**. This machine's
IIS already owns port 80 and routes by **host header** (each site has its own
hostname). So Aveon gets port 80 as its **own IIS site** that reverse-proxies to
the FastAPI backend on `127.0.0.1:8000`. Nothing else on this server is touched —
the existing `iclock` (eBioServerNew) site and the others keep working.

```
Remote device  --HTTP:80-->  IIS site (hostname)  --rewrite-->  uvicorn 127.0.0.1:8000
   Cloud Server = aveon.aveoniclock.com : 80 / iclock
```

## Prerequisites (install once, as Administrator)

Both are free Microsoft IIS modules and are **not currently installed** on this box:

1. **URL Rewrite 2.1** — https://www.iis.net/downloads/microsoft/url-rewrite
2. **Application Request Routing (ARR) 3.0** — https://www.iis.net/downloads/microsoft/application-request-routing

Install URL Rewrite first, then ARR. (If you have the Web Platform Installer:
`WebpiCmd /Install /Products:"UrlRewrite2,ARRv3_0"`.) An `iisreset` afterwards is
wise.

## Choose the hostname

Because routing is by host header, pick ONE of:

- **A. New hostname, run in parallel** (recommended, zero risk): e.g.
  `aveon.aveoniclock.com`. Add a public DNS A-record pointing at this server, and
  set the devices' Cloud Server to that hostname. The existing eBioServer keeps
  receiving its own devices on `www.aveoniclock.com`.

- **B. Reuse `www.aveoniclock.com`, migrate off eBioServer**: point the devices'
  existing hostname at Aveon instead. Do NOT create a second site on the same
  hostname — instead stop the existing `iclock` site and give this proxy that
  host header. Devices then need **no change** (they already use that hostname on
  port 80). Only do this when you are ready to retire eBioServerNew.

Remote devices are on the internet, so the hostname must resolve via **public
DNS**, and inbound TCP **80** must be forwarded to this server (you already do
this for `www.aveoniclock.com`, so the path exists).

## Set it up

In an **elevated** PowerShell:

```powershell
cd D:\ESSL\ESSL_SW\Aveon\deployment\iis
.\setup-iis-proxy.ps1 -HostName aveon.aveoniclock.com
```

The script enables the ARR proxy, creates the `AveonProxy` site bound to that
hostname on port 80, and points it at `web.config` here (which forwards
everything to `127.0.0.1:8000`, with the request-size limit raised for device
photo pushes).

## Verify

1. Backend running: `http://127.0.0.1:8000/health` -> `{"status":"ok"}`.
2. Through the proxy, from another machine:
   `http://aveon.aveoniclock.com/health` -> `{"status":"ok"}`.
3. Device push path: `http://aveon.aveoniclock.com/iclock/cdata?SN=<serial>&options=all`
   should return the plain-text option block.
4. On each device: **Comm. -> Cloud Server** = the hostname, **Port** = `80`,
   path `/iclock`. Within ~30s the device's **Last Ping** updates on the Devices
   page.

## Notes

- Keep the Aveon backend on `8000` (or pass `-BackendPort` to the script and it
  patches `web.config`). The admin UI (`:5173`) is unaffected and stays on the LAN.
- The proxy forwards `/api/v1` too, so if you want the admin UI reachable on port
  80 as well, you can later point the frontend's `VITE_API_BASE_URL` at
  `http://<hostname>/api/v1`.
