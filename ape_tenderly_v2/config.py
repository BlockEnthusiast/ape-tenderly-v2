from typing import Optional

from ape.api import PluginConfig
from pydantic_settings import SettingsConfigDict


class TenderlyConfig(PluginConfig):
    """``tenderly-v2:`` section of ``ape-config.yaml``.

    Credentials may live here or in the environment. The environment wins
    when both are set, and secrets belong in the environment:

        TENDERLY_ACCOUNT, TENDERLY_PROJECT, TENDERLY_ACCESS_KEY  (REST API)
        TENDERLY_GATEWAY_ACCESS_KEY                              (Node RPC)
    """

    account: Optional[str] = None
    project: Optional[str] = None
    access_key: Optional[str] = None
    gateway_access_key: Optional[str] = None
    """Tenderly Node access key. Without one the public, rate-limited gateway is used."""

    # ---- Virtual TestNets (``*-fork`` networks) ----
    auto_remove: bool = False
    """Delete a Virtual TestNet this process created when the provider disconnects."""

    sync_state: bool = False
    """Created vnets follow the live head instead of staying at the fork block."""

    block_number: Optional[int] = None
    """Fork block for created vnets. Default: ``latest``."""

    explorer: bool = False
    """Enable the public explorer page on created vnets."""

    label: str = "ape"
    """Slug prefix for created vnets."""

    request_timeout: int = 60

    chain_id: dict[str, dict[str, int]] = {}
    """Custom chain id for created vnets: ``chain_id.<ecosystem>.<network-fork>``.
    Default is the upstream chain's real id, so signatures and EIP-712 hashes
    match production."""

    rpc: dict[str, dict[str, str]] = {}
    """Pinned Admin RPC urls: ``rpc.<ecosystem>.<network-fork>``."""

    # ---- Node RPC gateway (live networks) ----
    gateway: dict[str, dict[str, str]] = {}
    """Full gateway url overrides: ``gateway.<ecosystem>.<network>``."""

    model_config = SettingsConfigDict(extra="allow")
