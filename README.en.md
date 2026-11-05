<div align="center">

<img src="frontend/public/favicon.svg" width="72" height="72" alt="Store Manager">

# Store Manager · warehouse for a small shop

Self-hosted web app: products with per-category attributes, suppliers, multi-item
receipts, detailed stats with Excel export, and barcode scanning on iPhone.

[![Release](https://img.shields.io/github/v/release/KROWIEL/warehouse-manager?color=0ea5e9)](https://github.com/KROWIEL/warehouse-manager/releases)
[![CI](https://github.com/KROWIEL/warehouse-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/KROWIEL/warehouse-manager/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)

**[Project site](https://krowiel.github.io/warehouse-manager/)** ·
**[Quick start](#quick-start)** ·
**[Русский](README.md)**

</div>

## Why

Cloud CRMs are often overkill for a small shop and keep your data elsewhere.
Store Manager is a single Docker image on your server: catalog, stock, sales and
Excel reports — no subscription, no third-party cloud.

## Screenshots

<p align="center">
  <img src="docs/screenshots/warehouse.png" width="48%" alt="Warehouse — product catalog">
  <img src="docs/screenshots/sale.png" width="48%" alt="Sale — multi-item receipt">
</p>
<p align="center">
  <img src="docs/screenshots/stats.png" width="48%" alt="Stats — revenue and charts">
  <img src="docs/screenshots/settings.png" width="48%" alt="Settings — profile and categories">
</p>
<p align="center">
  <img src="docs/screenshots/warehouse-dark.png" width="48%" alt="Warehouse — dark theme">
  <img src="docs/screenshots/mobile.png" width="28%" alt="Warehouse on phone">
</p>

## Features

- Categories, subcategories, suppliers, and configurable product attributes
- Stock as a movement journal (receipt, sale, return, write-off, inventory adjust)
- Multi-item receipts with discount, payment method, customer, negotiated price
- Stats for rolling or custom periods, breakdowns, dead/low stock
- Excel export (15 sheets + charts) and one-click SQLite backup
- PWA + camera barcode scanner (iOS included)
- No registration: accounts from `.env`, forced strong password on first login

## Quick start

```bash
git clone https://github.com/KROWIEL/warehouse-manager.git
cd warehouse-manager
cp .env.example .env
docker compose -f docker-compose.local.yml up -d --build
```

Open **http://localhost:8080**. For HTTPS with a domain, fill `DOMAIN` /
`ACME_EMAIL` in `.env` and run `docker compose up -d --build` (Caddy included).

## License

[MIT](LICENSE)
