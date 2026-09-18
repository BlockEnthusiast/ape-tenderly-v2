"""Which networks the plugin registers, their chain ids, and Tenderly's
gateway slugs for them.

Tenderly Node serves 75+ EVM chains and Virtual TestNets fork any of them.
The table below covers the ecosystems ape has plugins for; add a row to
extend. ``(ecosystem, network)`` keys use ape's names.
"""
from __future__ import annotations

#: (ecosystem, network) -> chain id
NETWORK_IDS: dict[tuple[str, str], int] = {
    ("ethereum", "mainnet"): 1,
    ("ethereum", "sepolia"): 11155111,
    ("ethereum", "holesky"): 17000,
    ("optimism", "mainnet"): 10,
    ("optimism", "sepolia"): 11155420,
    ("arbitrum", "mainnet"): 42161,
    ("arbitrum", "nova"): 42170,
    ("arbitrum", "sepolia"): 421614,
    ("base", "mainnet"): 8453,
    ("base", "sepolia"): 84532,
    ("polygon", "mainnet"): 137,
    ("polygon", "amoy"): 80002,
    ("avalanche", "mainnet"): 43114,
    ("avalanche", "fuji"): 43113,
    ("bsc", "mainnet"): 56,
    ("bsc", "testnet"): 97,
    ("blast", "mainnet"): 81457,
    ("blast", "sepolia"): 168587773,
    ("gnosis", "mainnet"): 100,
    ("linea", "mainnet"): 59144,
    ("scroll", "mainnet"): 534352,
    ("mantle", "mainnet"): 5000,
    ("sonic", "mainnet"): 146,
    ("berachain", "mainnet"): 80094,
    ("unichain", "mainnet"): 130,
    ("zksync", "mainnet"): 324,
    ("fantom", "opera"): 250,
    ("celo", "mainnet"): 42220,
    ("apechain", "mainnet"): 33139,
}

#: chains whose early blocks carry PoA extra-data; web3 needs the middleware
POA_CHAIN_IDS = {10, 11155420, 137, 80002, 56, 97, 8453, 84532, 100, 42220}

_GATEWAY_EXCEPTIONS: dict[tuple[str, str], str] = {
    ("ethereum", "mainnet"): "mainnet",
    ("fantom", "opera"): "fantom",
}


def chain_id(ecosystem: str, network: str) -> int:
    key = (ecosystem, network.replace("-fork", ""))
    if key not in NETWORK_IDS:
        raise KeyError(f"tenderly-v2: no chain id known for {key}; add it to networks.NETWORK_IDS")
    return NETWORK_IDS[key]


def gateway_slug(ecosystem: str, network: str) -> str:
    """Tenderly Node subdomain: ``mainnet``, ``sepolia``, ``optimism``,
    ``base-sepolia``, ``polygon-amoy`` ..."""
    key = (ecosystem, network)
    if key in _GATEWAY_EXCEPTIONS:
        return _GATEWAY_EXCEPTIONS[key]
    if ecosystem == "ethereum":
        return network
    if network == "mainnet":
        return ecosystem
    return f"{ecosystem}-{network}"


def gateway_url(ecosystem: str, network: str, access_key: str | None = None) -> str:
    base = f"https://{gateway_slug(ecosystem, network)}.gateway.tenderly.co"
    return f"{base}/{access_key}" if access_key else base


def live_networks():
    for eco, net in NETWORK_IDS:
        yield eco, net


def fork_networks():
    for eco, net in NETWORK_IDS:
        yield eco, f"{net}-fork"
