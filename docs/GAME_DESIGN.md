# BASHECO: approved concept (2026-11-12)

Persistent economic MMO on real Bashkortostan geography. Core loop: establish a company, procure inputs, produce or transport goods, trade, invest, and expand while the shared server-authoritative world changes.

## Decisions
- One persistent world, no economy shards or seasonal resets.
- Godot 4, touch-first Android APK, web and PC later; dark isometric 2.5D, hybrid regional map/city/company navigation.
- Real roads, waterways and recognizable settlement layout; stylized buildings; OSM licensing/attribution and geodata validation.
- Virtual land ownership, zoning, construction and renovation; no real-world property rights.
- Real-time calendar 1:1, displayed in Asia/Yekaterinburg (UTC+5), UTC timestamps in storage.
- Persistent production, inventories, trade, logistics, construction, agriculture, research, employees and households; offline operation limited by actual game resources.
- Hybrid onboarding: character, starting town, company, tutorial, starter capital and recovery path. Example 500,000 in-game rubles is provisional.
- Long-term: manufacturing chains, agriculture, player banks, loans, insurance, securities, corporations, government, reputation and social systems.
- Monetization: cosmetics, premium visuals and season pass, no pay-to-win, no conversion of premium tokens into economic money.
- Client never determines economic outcomes or balances.

## MVP
Accounts, companies, a small test district of Ufa, starter enterprise, production, inventory, basic trade, offline progression, and Android client.

## Deployment
Repository maillunex-lang/basheco; planned https://rikagro.ru/basheco/ and APK updates. VPS and existing services must be audited separately before any authorized deployment. Stage 1 does not touch VPS.
