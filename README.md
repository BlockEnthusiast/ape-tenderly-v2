# ape-tenderly-v2

[Tenderly](https://tenderly.co) for [ape](https://apeworx.io), covering Tenderly's current
products under one plugin name, `tenderly-v2`:

| Role | Network choice | What it is |
|---|---|---|
| Fork test provider | `ethereum:mainnet-fork:tenderly-v2` | A **Virtual TestNet** with the full `TestProviderAPI`: snapshot and revert, impersonation, balance, code and storage cheats, mining, time travel, plus Tenderly's ERC-20 and time extras. |
| Live upstream provider | `ethereum:mainnet:tenderly-v2` | **Tenderly Node** RPC, like `ape-alchemy` or `ape-infura`. |
| Explorer | automatic on both | Dashboard links for transactions and addresses, public contract ABIs, and (experimental) verification. |
| CLI | `ape tenderly-v2 ...` | Create, list, inspect, delete and prune Virtual TestNets. Run Simulation API calls. |

Anything written for `ape-foundry` (anvil) runs on a remote Virtual TestNet with one
network-choice change:

```bash
ape run my_script --network ethereum:mainnet-fork:foundry      # local anvil
ape run my_script --network ethereum:mainnet-fork:tenderly-v2  # remote Virtual TestNet
ape test --network ethereum:mainnet-fork:tenderly-v2
```

## Why not ApeWorX's `ape-tenderly`

[`ape-tenderly`](https://github.com/ApeWorX/ape-tenderly) targets the legacy Tenderly Forks
API, which Tenderly has [scheduled for deprecation](https://blog.tenderly.co/changelog/forks-deprecation-scheduled/)
in favour of Virtual TestNets. Its fork provider subclasses plain `Web3Provider`, so
`accounts[addr]` impersonation, `provider.snapshot()`, and `provider.set_balance()` all
fail on it. Its [issue #19](https://github.com/ApeWorX/ape-tenderly/issues/19) asks for
exactly the two changes made here: target Virtual TestNets and subclass `TestProviderAPI`.

## Install

```bash
pip install -e .
ape plugins list        # tenderly-v2 under third-party plugins
```

Networks registered: `mainnet` and `mainnet-fork` (and testnets) for ethereum, optimism,
arbitrum, base, polygon, avalanche, bsc, blast, gnosis, linea, scroll, mantle, sonic,
berachain, unichain, zksync, fantom, celo and apechain. See
[`networks.py`](ape_tenderly_v2/networks.py) to add one.

## Credentials

Environment first, then `ape-config.yaml`. Keep secrets in the environment.

```bash
export TENDERLY_ACCOUNT=<account slug>        # REST API: vnets, simulations, verification
export TENDERLY_PROJECT=<project slug>
export TENDERLY_ACCESS_KEY=<access key>
export TENDERLY_GATEWAY_ACCESS_KEY=<node key> # Node RPC; omit for the public rate-limited gateway
```

## Virtual TestNets (`*-fork` networks)

Where the vnet comes from, in order:

1. `provider_settings={"uri": "<Admin RPC url>"}` passed by the caller.
2. `tenderly-v2.rpc.<ecosystem>.<network-fork>` in `ape-config.yaml`.
3. The vnet this machine created earlier, recorded in `~/.ape/tenderly_v2/vnets.json`.
4. A new vnet created through the REST API with the credentials above.

Created vnets fork the upstream network at `latest` (or `block_number`) with the **real
chain id** unless `chain_id` overrides it, and state sync off unless `sync_state: true`.
So they behave like a pinned anvil fork, and signatures and EIP-712 hashes match
production. `provider.restart()` creates a fresh vnet at head and deletes the previous
recorded one.

Method mapping onto the Admin RPC:

| `TestProviderAPI` | sent |
|---|---|
| `snapshot` / `restore` | `evm_snapshot` / `evm_revert` (revert reaches back at most 2000 blocks) |
| `unlock_account` / `relock_account` | nothing: the Admin RPC accepts unsigned `eth_sendTransaction` from any sender |
| `set_balance` | `tenderly_setBalance` |
| `set_code` | `tenderly_setCode` |
| `set_storage` | `tenderly_setStorageAt` |
| `mine` | `evm_increaseBlocks` |
| `set_timestamp` | `evm_setNextBlockTimestamp` |

Extras on the provider: `add_balance`, `set_erc20_balance`, `add_erc20_balance` (emits a
synthetic `Transfer`), `deal_erc20` (ape-foundry's signature), `increase_time`,
`increase_blocks`, `set_next_block_timestamp` (no mining), `create_vnet`, `restart`,
`record`, `dashboard_url`.

## Tenderly Node (live networks)

```bash
ape console --network ethereum:mainnet:tenderly-v2
```

URL: `https://<slug>.gateway.tenderly.co/<TENDERLY_GATEWAY_ACCESS_KEY>`. Without a key
the public endpoint is used with its rate limits. Pin a full url per network with
`tenderly-v2.gateway.<ecosystem>.<network>`.

## CLI

```bash
ape tenderly-v2 vnets list
ape tenderly-v2 vnets create --ecosystem ethereum --network mainnet [--block N] [--chain-id N] [--sync-state] [--explorer]
ape tenderly-v2 vnets show <id>
ape tenderly-v2 vnets rpc --ecosystem base --network mainnet [--public]
ape tenderly-v2 vnets delete <id>
ape tenderly-v2 vnets prune --label ape --yes      # bulk delete by slug prefix, keeps recorded vnets
ape tenderly-v2 simulate --from 0x... --to 0x... --input 0x... [--block N] [--json]
ape tenderly-v2 gateway-url --ecosystem optimism --network mainnet
```

`vnets create` records the new vnet as the one the provider uses for that network, so
`--network ...-fork:tenderly-v2` picks it up next.

## Simulation API

```python
from ape_tenderly_v2 import TenderlyClient
from ape_tenderly_v2.client import Credentials

client = TenderlyClient(Credentials.resolve())
res = client.simulate(network_id=1, from_=safe, to=vault, input=calldata)
print(TenderlyClient.simulation_summary(res))   # status, gas, error, asset_changes, url
results = client.simulate_bundle(network_id=1, transactions=[{...}, {...}])
```

Simulations are stateless runs on the live chain state (or a block). For stateful work,
use a Virtual TestNet through the provider.

## Config

```yaml
tenderly-v2:
  account: my-account       # or TENDERLY_ACCOUNT
  project: my-project       # or TENDERLY_PROJECT
  # access_key / gateway_access_key: use the environment
  auto_remove: false        # delete a vnet this process created on disconnect
  sync_state: false         # created vnets follow the live head
  block_number: null        # fork block for created vnets (default latest)
  explorer: false           # public explorer page on created vnets
  label: ape                # slug prefix for created vnets
  request_timeout: 60
  chain_id:                 # custom chain id for created vnets (default: real)
    ethereum:
      mainnet-fork: 73571
  rpc:                      # pinned Admin RPC urls
    ethereum:
      mainnet-fork: https://virtual.mainnet.rpc.tenderly.co/<id>
  gateway:                  # full Node RPC url overrides
    ethereum:
      mainnet: https://mainnet.gateway.tenderly.co/<key>
```

## Explorer

On live networks `ape` links go to `dashboard.tenderly.co/tx/<slug>/<hash>` and
`dashboard.tenderly.co/contract/<slug>/<address>`. On a `tenderly-v2` fork they go to the
project's Virtual TestNet page. `get_contract_type` reads Tenderly's public contract data.
`publish_contract` posts to the project verification endpoint and is **experimental**:
check the response before relying on it.

## Tests

```bash
pip install -e .[test]
pytest
```

The tests run against a fake Admin RPC and a mocked REST layer. No Tenderly account is
needed.

## Status

- Verified through ape against a fake Admin RPC: impersonated accounts, every cheat call
  reaching the wire under its Tenderly name, uri resolution order, REST bookkeeping.
- The REST and RPC shapes follow Tenderly's own GitHub Action
  (`Tenderly/vnet-github-action`) and the Admin RPC docs.
- Not yet exercised against a live Virtual TestNet or Tenderly Node. Verification and the
  public-contract lookup are best-effort until then.

## License

Apache-2.0.
