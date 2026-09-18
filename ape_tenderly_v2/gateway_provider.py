"""``tenderly-v2`` on live networks: Tenderly Node RPC as an ape upstream
provider, like ``ape-alchemy`` or ``ape-infura``.

URL: ``https://<slug>.gateway.tenderly.co/<TENDERLY_GATEWAY_ACCESS_KEY>``.
Without a key the public, rate-limited endpoint is used. A full url may be
pinned per network with ``tenderly-v2.gateway.<ecosystem>.<network>``.
"""
from __future__ import annotations

import os
from typing import Optional

from ape.api import UpstreamProvider
from ape.exceptions import ProviderError
from ape.logging import logger
from ape_ethereum.provider import Web3Provider
from web3 import HTTPProvider, Web3
from web3.gas_strategies.rpc import rpc_gas_price_strategy

from . import client as tc
from . import networks
from .config import TenderlyConfig

try:
    from web3.middleware import ExtraDataToPOAMiddleware  # type: ignore
except ImportError:  # web3 < 7
    from web3.middleware import geth_poa_middleware as ExtraDataToPOAMiddleware  # type: ignore


class TenderlyGatewayProvider(Web3Provider, UpstreamProvider):
    _web3: Optional[Web3] = None

    @property
    def settings(self) -> TenderlyConfig:  # type: ignore[override]
        return super().settings  # type: ignore[return-value]

    @property
    def gateway_access_key(self) -> Optional[str]:
        return os.environ.get("TENDERLY_GATEWAY_ACCESS_KEY") or self.settings.gateway_access_key

    @property
    def uri(self) -> str:
        if u := self.provider_settings.get("uri"):
            return u
        eco, net = self.network.ecosystem.name, self.network.name
        if u := (self.settings.gateway.get(eco) or {}).get(net):
            return u
        return networks.gateway_url(eco, net, self.gateway_access_key)

    @property
    def http_uri(self) -> str:
        return self.uri

    @property
    def ws_uri(self) -> Optional[str]:
        u = self.uri
        return "wss://" + u[len("https://"):] if u.startswith("https://") else None

    @property
    def connection_str(self) -> str:
        return tc.redact(self.uri) or self.uri

    @property
    def connection_id(self) -> Optional[str]:
        return self.connection_str

    def connect(self):
        uri = self.uri
        self._web3 = Web3(HTTPProvider(
            uri, request_kwargs={"timeout": self.settings.request_timeout}))
        try:
            chain_id = self._web3.eth.chain_id
        except Exception as err:
            raise ProviderError(
                f"tenderly-v2: failed to connect to Tenderly Node at {tc.redact(uri)}: {err!r}"
            ) from err
        try:
            expected = networks.chain_id(self.network.ecosystem.name, self.network.name)
        except KeyError:
            expected = None
        if expected is not None and chain_id != expected:
            raise ProviderError(
                f"tenderly-v2: {tc.redact(uri)} reports chain id {chain_id}, "
                f"expected {expected} for {self.network.choice}")
        if chain_id in networks.POA_CHAIN_IDS:
            self._web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self._web3.eth.set_gas_price_strategy(rpc_gas_price_strategy)
        if not self.gateway_access_key:
            logger.warning("tenderly-v2: no TENDERLY_GATEWAY_ACCESS_KEY, using the public "
                           "rate-limited gateway")

    def disconnect(self):
        self._web3 = None
