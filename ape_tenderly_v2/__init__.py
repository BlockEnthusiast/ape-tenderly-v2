"""ape-tenderly-v2: Tenderly for ape, current products.

Registers one plugin name, ``tenderly-v2``, in three roles:

* **provider on ``*-fork`` networks**: a Tenderly Virtual TestNet with the
  full ``TestProviderAPI`` (snapshot/revert, impersonation, balance, code,
  storage, mining, time travel) plus Tenderly's extra cheats.
* **provider on live networks**: Tenderly Node RPC as an upstream provider.
* **explorer**: dashboard links, public contract types, verification.

Plus ``ape tenderly-v2 vnets ...`` and ``ape tenderly-v2 simulate`` commands.

    --network ethereum:mainnet:tenderly-v2       # Tenderly Node (live)
    --network ethereum:mainnet-fork:tenderly-v2  # Virtual TestNet (fork)

ApeWorX's ``ape-tenderly`` targets the deprecated Tenderly Forks API and
subclasses plain ``Web3Provider``, so impersonation, snapshots and cheats do
not work on it; this plugin is the Virtual TestNet successor its issue #19
asks for.
"""

from ape import plugins


@plugins.register(plugins.Config)
def config_class():
    from .config import TenderlyConfig

    return TenderlyConfig


@plugins.register(plugins.ProviderPlugin)
def providers():
    from .gateway_provider import TenderlyGatewayProvider
    from .networks import fork_networks, live_networks
    from .vnet_provider import TenderlyVnetProvider

    for eco, net in live_networks():
        yield eco, net, TenderlyGatewayProvider
    for eco, net in fork_networks():
        yield eco, net, TenderlyVnetProvider


@plugins.register(plugins.ExplorerPlugin)
def explorers():
    from .explorer import TenderlyExplorer
    from .networks import fork_networks, live_networks

    for eco, net in live_networks():
        yield eco, net, TenderlyExplorer
    for eco, net in fork_networks():
        yield eco, net, TenderlyExplorer


def __getattr__(name: str):
    if name == "TenderlyVnetProvider":
        from .vnet_provider import TenderlyVnetProvider

        return TenderlyVnetProvider
    if name == "TenderlyGatewayProvider":
        from .gateway_provider import TenderlyGatewayProvider

        return TenderlyGatewayProvider
    if name == "TenderlyExplorer":
        from .explorer import TenderlyExplorer

        return TenderlyExplorer
    if name == "TenderlyConfig":
        from .config import TenderlyConfig

        return TenderlyConfig
    if name == "TenderlyClient":
        from .client import TenderlyClient

        return TenderlyClient
    raise AttributeError(name)


__all__ = ["TenderlyVnetProvider", "TenderlyGatewayProvider", "TenderlyExplorer",
           "TenderlyConfig", "TenderlyClient"]
