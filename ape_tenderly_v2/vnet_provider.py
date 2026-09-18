"""``tenderly-v2`` on ``*-fork`` networks: an ape test provider backed by a
Tenderly Virtual TestNet.

A Virtual TestNet is a hosted fork with a JSON-RPC endpoint. Its **Admin
RPC** accepts unsigned ``eth_sendTransaction`` from any ``from`` address and
exposes cheat methods. This provider maps ape's ``TestProviderAPI`` onto
them, the way ``ape-foundry`` maps it onto anvil's ``anvil_*`` methods, and
adds Tenderly's extra cheats (ERC-20 balances, time/block jumps).

Where the vnet comes from, in order:

1. ``provider_settings={"uri": ...}`` passed by the caller
2. ``tenderly-v2.rpc.<ecosystem>.<network-fork>`` in ``ape-config.yaml``
3. the vnet this machine created earlier (``~/.ape/tenderly_v2/vnets.json``)
4. a new vnet created through the REST API (needs ``TENDERLY_ACCOUNT`` /
   ``TENDERLY_PROJECT`` / ``TENDERLY_ACCESS_KEY``, or the same keys in config)

Created vnets fork the upstream network at ``latest`` (or ``block_number``)
with the **real chain id** unless ``chain_id`` overrides it, and state sync
off unless ``sync_state: true``, so they behave like a pinned anvil fork.
``restart()`` replaces the vnet with a fresh one at head.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ape.api import TestProviderAPI
from ape.exceptions import ProviderError
from ape.logging import logger
from ape_ethereum.provider import Web3Provider
from eth_pydantic_types import HexBytes32
from eth_pydantic_types.hex.bytes import PadDirection
from eth_utils import add_0x_prefix, is_0x_prefixed, is_hex, to_hex
from hexbytes import HexBytes
from web3 import HTTPProvider, Web3

from . import client as tc
from . import networks
from .config import TenderlyConfig

if TYPE_CHECKING:
    from ape.types import AddressType, ContractCode, SnapshotID

try:
    from web3.middleware import ExtraDataToPOAMiddleware  # type: ignore
except ImportError:  # web3 < 7
    from web3.middleware import geth_poa_middleware as ExtraDataToPOAMiddleware  # type: ignore


class TenderlyVnetProvider(Web3Provider, TestProviderAPI):
    _web3: Optional[Web3] = None
    _record: Optional[dict] = None
    _created_here: bool = False

    # ----------------------------------------------------------- identity

    @property
    def settings(self) -> TenderlyConfig:  # type: ignore[override]
        return super().settings  # type: ignore[return-value]

    @property
    def upstream_network(self) -> str:
        return self.network.name.replace("-fork", "")

    @property
    def network_id(self) -> int:
        try:
            return networks.chain_id(self.network.ecosystem.name, self.upstream_network)
        except KeyError as e:
            raise ProviderError(str(e)) from e

    @property
    def vnet_chain_id(self) -> int:
        eco = self.network.ecosystem.name
        override = (self.settings.chain_id.get(eco) or {}).get(self.network.name)
        return int(override) if override else self.network_id

    @property
    def records_path(self) -> Path:
        return Path(self.config_manager.DATA_FOLDER) / "tenderly_v2" / "vnets.json"

    @property
    def record_key(self) -> str:
        return f"{self.network.ecosystem.name}:{self.network.name}"

    @property
    def record(self) -> Optional[dict]:
        return self._record or tc.load_records(self.records_path).get(self.record_key)

    @property
    def client(self) -> tc.TenderlyClient:
        creds = tc.Credentials.resolve(self.settings.account, self.settings.project,
                                       self.settings.access_key)
        if creds is None:
            raise ProviderError(
                "tenderly-v2: TENDERLY_ACCOUNT / TENDERLY_PROJECT / TENDERLY_ACCESS_KEY "
                "are not set (env or tenderly-v2 config) — cannot manage Virtual TestNets")
        return tc.TenderlyClient(creds, timeout=self.settings.request_timeout)

    # ----------------------------------------------------------- uri

    @property
    def uri(self) -> str:
        if u := self.provider_settings.get("uri"):
            return u
        eco = self.network.ecosystem.name
        if u := (self.settings.rpc.get(eco) or {}).get(self.network.name):
            return u
        if rec := self.record:
            return rec["admin_rpc"]
        raise ProviderError(
            f"tenderly-v2: no Virtual TestNet for {self.record_key}. Pass "
            f"provider_settings={{'uri': <Admin RPC>}}, set tenderly-v2.rpc.{eco}."
            f"{self.network.name} in ape-config.yaml, or set TENDERLY_ACCOUNT / "
            f"TENDERLY_PROJECT / TENDERLY_ACCESS_KEY so one can be created.")

    @property
    def http_uri(self) -> Optional[str]:
        try:
            return self.uri
        except ProviderError:
            return None

    @property
    def connection_str(self) -> str:
        return tc.redact(self.http_uri) or "tenderly-v2 (unresolved)"

    @property
    def connection_id(self) -> Optional[str]:
        return self.connection_str

    @property
    def dashboard_url(self) -> Optional[str]:
        rec = self.record
        if not rec or not rec.get("id"):
            return None
        try:
            return self.client.vnet_url(rec["id"])
        except ProviderError:
            return None

    # ----------------------------------------------------------- lifecycle

    def create_vnet(self) -> dict:
        """Create a fresh vnet for this network, record it, and delete the
        previously recorded one (best effort)."""
        client = self.client
        block: str | int = self.settings.block_number or "latest"
        rec = client.create_vnet(
            network_id=self.network_id, chain_id=self.vnet_chain_id, block=block,
            sync_state=self.settings.sync_state, explorer=self.settings.explorer,
            label=self.settings.label)
        records = tc.load_records(self.records_path)
        old = records.get(self.record_key) or {}
        records[self.record_key] = rec
        tc.save_records(self.records_path, records)
        if old.get("id") and old["id"] != rec["id"] and client.delete_vnet(old["id"]):
            logger.info(f"tenderly-v2: deleted previous vnet {old['id']}")
        logger.success(f"tenderly-v2: created {rec['slug']} at block {rec['block']}")
        self._record = rec
        self._created_here = True
        return rec

    def connect(self):
        try:
            uri = self.uri
        except ProviderError:
            uri = self.create_vnet()["admin_rpc"]
        self._web3 = Web3(HTTPProvider(
            uri, request_kwargs={"timeout": self.settings.request_timeout}))
        try:
            chain_id = self._web3.eth.chain_id
        except Exception as err:
            raise ProviderError(
                f"tenderly-v2: failed to connect to {tc.redact(uri)}: {err!r}") from err
        if chain_id in networks.POA_CHAIN_IDS:
            self._web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        logger.info(f"tenderly-v2: connected to {tc.redact(uri)} (chain id {chain_id})")

    def disconnect(self):
        if self.settings.auto_remove and self._created_here and self._record:
            try:
                if self.client.delete_vnet(self._record["id"]):
                    records = tc.load_records(self.records_path)
                    if (records.get(self.record_key) or {}).get("id") == self._record["id"]:
                        records.pop(self.record_key, None)
                        tc.save_records(self.records_path, records)
                    logger.info(f"tenderly-v2: removed {self._record['slug']}")
            except Exception as err:  # noqa: BLE001
                logger.error(f"tenderly-v2: could not remove vnet: {err}")
        self._web3 = None
        self._record = None
        self._created_here = False

    def restart(self) -> dict:
        """Replace the vnet with a fresh one at head and reconnect."""
        if self.provider_settings.get("uri"):
            raise ProviderError(
                "tenderly-v2: this connection pins a uri; recreate that vnet in the "
                "Tenderly dashboard or drop the pin so restart can manage it")
        self._web3 = None
        rec = self.create_vnet()
        self.connect()
        return rec

    # ----------------------------------------------------------- TestProviderAPI

    @property
    def auto_mine(self) -> bool:
        return True

    @auto_mine.setter
    def auto_mine(self, value):
        if not value:
            raise ProviderError("tenderly-v2: manual mining is not supported")

    def snapshot(self) -> "SnapshotID":
        return self.make_request("evm_snapshot", [])

    def restore(self, snapshot_id: "SnapshotID"):
        result = self.make_request("evm_revert", [snapshot_id])
        return result is True or result is None or bool(result)

    def set_timestamp(self, new_timestamp: int):
        self.make_request("evm_setNextBlockTimestamp", [str(int(new_timestamp))])

    def mine(self, num_blocks: int = 1):
        self.make_request("evm_increaseBlocks", [to_hex(int(num_blocks))])

    def set_balance(self, account: "AddressType", amount: Any):
        self.make_request("tenderly_setBalance", [account, self._hex_amount(amount)])

    def set_code(self, address: "AddressType", code: "ContractCode") -> bool:
        if isinstance(code, bytes):
            code = to_hex(code)
        elif isinstance(code, str) and not is_0x_prefixed(code):
            code = add_0x_prefix(code)  # type: ignore[arg-type]
        elif not is_hex(code):
            raise ValueError(f"Value {code} is not convertible to hex")
        self.make_request("tenderly_setCode", [address, code])
        return True

    def set_storage(self, address: "AddressType", slot: int, value: HexBytes):
        self.make_request("tenderly_setStorageAt", [
            address,
            to_hex(HexBytes32.__eth_pydantic_validate__(slot, pad=PadDirection.LEFT)),
            to_hex(HexBytes32.__eth_pydantic_validate__(value, pad=PadDirection.LEFT)),
        ])

    def unlock_account(self, address: "AddressType") -> bool:
        # The Admin RPC accepts unsigned transactions from any sender.
        return True

    def relock_account(self, address: "AddressType"):
        return None

    # ----------------------------------------------------------- Tenderly extras

    def add_balance(self, account: "AddressType", amount: Any):
        self.make_request("tenderly_addBalance", [account, self._hex_amount(amount)])

    def set_erc20_balance(self, token: "AddressType", account: "AddressType", amount: Any):
        self.make_request("tenderly_setErc20Balance", [token, account, self._hex_amount(amount)])

    def add_erc20_balance(self, token: "AddressType", account: "AddressType", amount: Any):
        """Like set_erc20_balance but emits a synthetic Transfer event."""
        self.make_request("tenderly_addErc20Balance", [token, account, self._hex_amount(amount)])

    def deal_erc20(self, address: "AddressType", token_address: "AddressType", amount: int):
        """Same signature as ape-foundry's ``deal_erc20`` so scripts port unchanged."""
        self.set_erc20_balance(token_address, address, amount)

    def increase_time(self, seconds: int):
        self.make_request("evm_increaseTime", [to_hex(int(seconds))])

    def increase_blocks(self, num_blocks: int):
        self.make_request("evm_increaseBlocks", [to_hex(int(num_blocks))])

    def set_next_block_timestamp(self, timestamp: int):
        """Set the next block's timestamp without mining (Tenderly-specific)."""
        self.make_request("tenderly_setNextBlockTimestamp", [str(int(timestamp))])

    def _hex_amount(self, amount: Any) -> str:
        if isinstance(amount, str):
            if amount.startswith("0x"):
                return amount
            amount = self.conversion_manager.convert(amount, int)
        if isinstance(amount, bytes):
            return to_hex(amount)
        return to_hex(int(amount))
