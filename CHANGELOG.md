# Changelog

## 0.1.0 (2026-09-18)

First release.

- `tenderly-v2` provider on `*-fork` networks: Tenderly Virtual TestNet with the full
  `TestProviderAPI` (snapshot/restore, unlock/relock, set_balance, set_code, set_storage,
  mine, set_timestamp) and Tenderly extras (add_balance, set/add_erc20_balance,
  deal_erc20, increase_time, increase_blocks, set_next_block_timestamp).
- Vnet lifecycle: create through the REST API with real chain id, record under
  `~/.ape/tenderly_v2/vnets.json`, `restart()` to replace, optional `auto_remove`.
- `tenderly-v2` provider on live networks: Tenderly Node RPC as an upstream provider,
  keyed or public.
- Explorer: dashboard transaction and address urls (live and vnet), public contract types,
  experimental verification.
- CLI: `ape tenderly-v2 vnets list|create|show|rpc|delete|prune`, `simulate`,
  `gateway-url`.
- `TenderlyClient`: vnets CRUD, `simulate`, `simulate_bundle`, `simulation_summary`,
  `verify_contract`, dashboard urls.
