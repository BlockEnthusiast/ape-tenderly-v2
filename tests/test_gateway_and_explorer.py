from conftest import MS


def test_gateway_uri_resolution(monkeypatch, no_creds):
    from ape import networks

    net = networks.ethereum.mainnet
    p = net.get_provider("tenderly-v2")
    assert p.uri == "https://mainnet.gateway.tenderly.co"
    assert p.ws_uri == "wss://mainnet.gateway.tenderly.co"
    monkeypatch.setenv("TENDERLY_GATEWAY_ACCESS_KEY", "abcdefgh12345")
    p = net.get_provider("tenderly-v2")
    assert p.uri == "https://mainnet.gateway.tenderly.co/abcdefgh12345"
    assert p.connection_str.endswith("…h12345") and "abcdefgh" not in p.connection_str
    p = net.get_provider("tenderly-v2", provider_settings={"uri": "https://x.example/rpc"})
    assert p.uri == "https://x.example/rpc"
    p = networks.optimism.mainnet.get_provider("tenderly-v2")
    assert p.uri.startswith("https://optimism.gateway.tenderly.co/")


def test_gateway_connects_and_checks_chain(fake_rpc, no_creds):
    from ape import networks

    with networks.parse_network_choice("ethereum:mainnet:tenderly-v2",
                                       provider_settings={"uri": fake_rpc}) as p:
        assert p.chain_id == 1
        assert p.name == "tenderly-v2"


def test_explorer_registered_and_urls(fake_rpc, no_creds):
    from ape import networks

    net = networks.ethereum.mainnet
    ex = net.explorer
    assert ex is not None and type(ex).__name__ == "TenderlyExplorer"
    assert ex.get_transaction_url("0xh") == "https://dashboard.tenderly.co/tx/mainnet/0xh"
    assert ex.get_address_url(MS) == f"https://dashboard.tenderly.co/contract/mainnet/{MS}"
    fork = networks.ethereum.mainnet_fork
    fex = fork.explorer
    assert type(fex).__name__ == "TenderlyExplorer"
    # without an active vnet provider the fork explorer falls back to public pages
    assert fex.get_transaction_url("0xh") == "https://dashboard.tenderly.co/tx/mainnet/0xh"


def test_explorer_links_into_vnet(fake_rpc, monkeypatch, isolated_records):
    from ape import networks
    from ape_tenderly_v2 import client as tc

    monkeypatch.setenv("TENDERLY_ACCOUNT", "acct")
    monkeypatch.setenv("TENDERLY_PROJECT", "proj")
    monkeypatch.setenv("TENDERLY_ACCESS_KEY", "key")
    tc.save_records(isolated_records, {"ethereum:mainnet-fork": {"id": "vnet-9", "admin_rpc": fake_rpc}})
    with networks.parse_network_choice("ethereum:mainnet-fork:tenderly-v2") as p:
        ex = p.network.explorer
        assert ex.get_transaction_url("0xh") == "https://dashboard.tenderly.co/acct/proj/testnet/vnet-9/tx/0xh"
        assert ex.get_address_url(MS).startswith("https://dashboard.tenderly.co/acct/proj/testnet/vnet-9/contract/")


def test_explorer_contract_type(monkeypatch, no_creds):
    from ape import networks
    from ape_tenderly_v2 import client as tc

    abi = [{"type": "function", "name": "foo", "inputs": [], "outputs": [], "stateMutability": "view"}]
    monkeypatch.setattr(tc.TenderlyClient, "public_contract",
                        staticmethod(lambda nid, addr, timeout=30: {"contract_name": "Foo", "abi": abi}))
    ct = networks.ethereum.mainnet.explorer.get_contract_type(MS)
    assert ct is not None and ct.name == "Foo" and "foo" in ct.methods
    monkeypatch.setattr(tc.TenderlyClient, "public_contract",
                        staticmethod(lambda nid, addr, timeout=30: None))
    assert networks.ethereum.mainnet.explorer.get_contract_type(MS) is None
