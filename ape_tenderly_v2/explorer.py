"""Tenderly dashboard as an ape explorer: transaction and address links,
contract types from Tenderly's public contract data, and (experimental)
verification through the project API.

Live networks link to the public dashboard pages
(``dashboard.tenderly.co/tx/<slug>/<hash>``). ``*-fork`` networks served by
the ``tenderly-v2`` provider link into the project's Virtual TestNet page.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ape.api import ExplorerAPI
from ape.logging import logger

from . import client as tc
from . import networks

if TYPE_CHECKING:
    from ape.types import AddressType
    from ethpm_types import ContractType


class TenderlyExplorer(ExplorerAPI):
    @property
    def _is_fork(self) -> bool:
        return self.network.name.endswith("-fork")

    @property
    def _slug(self) -> str:
        return networks.gateway_slug(self.network.ecosystem.name,
                                     self.network.name.replace("-fork", ""))

    def _vnet(self) -> tuple[Optional[tc.TenderlyClient], Optional[str]]:
        """(client, vnet id) when the active provider is a tenderly-v2 vnet."""
        provider = self.network_manager.active_provider
        rec = getattr(provider, "record", None)
        if not isinstance(rec, dict) or not rec.get("id"):
            return None, None
        try:
            return provider.client, rec["id"]  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            return None, None

    def get_transaction_url(self, transaction_hash: str) -> str:
        if self._is_fork:
            client, vnet_id = self._vnet()
            if client and vnet_id:
                return client.vnet_transaction_url(vnet_id, transaction_hash)
        return tc.TenderlyClient.public_transaction_url(self._slug, transaction_hash)

    def get_address_url(self, address: "AddressType") -> str:
        if self._is_fork:
            client, vnet_id = self._vnet()
            if client and vnet_id:
                return f"{client.vnet_url(vnet_id)}/contract/{address}"
        return tc.TenderlyClient.public_contract_url(self._slug, address)

    def get_contract_type(self, address: "AddressType") -> Optional["ContractType"]:
        try:
            network_id = networks.chain_id(self.network.ecosystem.name, self.network.name)
        except KeyError:
            return None
        data = tc.TenderlyClient.public_contract(network_id, address)
        if not data:
            return None
        abi = data.get("abi") or (data.get("contract") or {}).get("abi")
        if not abi:
            return None
        from ethpm_types import ContractType

        name = data.get("contract_name") or (data.get("contract") or {}).get("contract_name") \
            or "Contract"
        try:
            return ContractType(contractName=name, abi=abi)
        except Exception as err:  # noqa: BLE001
            logger.debug(f"tenderly-v2: could not build ContractType for {address}: {err}")
            return None

    def publish_contract(self, address: "AddressType"):
        """Experimental: verify the contract in the Tenderly project from the
        local project's compiled sources."""
        contract_type = self.chain_manager.contracts.get(address)
        if contract_type is None:
            raise ValueError(f"tenderly-v2: no contract type cached for {address}")
        settings = self.config_manager.get_config("tenderly-v2")
        creds = tc.Credentials.resolve(getattr(settings, "account", None),
                                       getattr(settings, "project", None),
                                       getattr(settings, "access_key", None))
        if creds is None:
            raise ValueError("tenderly-v2: TENDERLY_ACCOUNT / TENDERLY_PROJECT / "
                             "TENDERLY_ACCESS_KEY are required to publish")
        source_id = contract_type.source_id
        if not source_id:
            raise ValueError(f"tenderly-v2: {contract_type.name} has no source id")
        source_path = self.local_project.path / source_id
        sources = {source_id: source_path.read_text()}
        compiler = next((c for c in self.local_project.manifest.compilers or []
                         if contract_type.name in (c.contractTypes or [])), None)
        version = compiler.version if compiler else "0.8.0"
        opt = (compiler.settings or {}).get("optimizer", {}) if compiler else {}
        network_id = networks.chain_id(self.network.ecosystem.name, self.network.name)
        return tc.TenderlyClient(creds).verify_contract(
            network_id=network_id, address=address, contract_name=contract_type.name,
            sources=sources, compiler_version=version,
            optimizer_enabled=bool(opt.get("enabled")), optimizer_runs=int(opt.get("runs", 200)),
            evm_version=(compiler.settings or {}).get("evmVersion") if compiler else None)
