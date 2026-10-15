# Aveon deployment

**Client server install:** see [DEPLOYMENT-STEPS.md](DEPLOYMENT-STEPS.md).

```powershell
.\build-client-package.ps1 -DownloadPrereqs -CreateZip   # -> out\AveonSetup.zip
```

Copy the zip to the client, extract it, and double-click `INSTALL.cmd`.

| Path | Purpose |
|---|---|
| `build-client-package.ps1` | builds the offline one-click package |
| `installer\` | `INSTALL.cmd`, `UNINSTALL.cmd`, `install.ps1`, config, task/env templates, 32-bit SDK |
| `prereqs\` | cached, signature-checked prerequisite installers (filled by `-DownloadPrereqs`) |
| `health-watchdog.ps1` | per-minute health watchdog (shipped with every install) |
| `iis\` | host-header reverse-proxy and hostname cut-over scripts (eBioServer migrations) |
| `Aveon*.xml`, `setup-resilient-services.ps1`, `repair-*.ps1` | this development machine's own service setup |

Manuals: `docs\Client-Installation-Manual.md`, `docs\User-Manual.md`.
