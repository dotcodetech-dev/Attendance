Logo Provision
==============

You can add your own company logo without code changes.

Option 1 (default path)
-----------------------
1. Copy your logo file to:
   frontend/public/branding/logo.png
2. Restart frontend dev server if needed.

Option 2 (custom path via .env)
-------------------------------
1. Place your logo file anywhere under frontend/public
   Example: frontend/public/branding/my-company-logo.png
2. Set in frontend/.env:
   VITE_BRAND_LOGO_URL=/branding/my-company-logo.png
3. Restart frontend dev server.

Notes
-----
- Supported by browser formats: png, jpg, jpeg, svg, webp
- If custom logo cannot be loaded, system automatically falls back to built-in Aveon logo.
