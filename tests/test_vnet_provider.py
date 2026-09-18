import pytest
from conftest import MS, TOKEN, FakeAdminRpc, wire


def test_registered_on_fork_and_live_networks():
    from ape import networks
    assert "tenderly-v2" in networks.ethereum.mainnet_fork.providers
    assert "tenderly-v2" in networks.ethereum.mainnet.providers
    assert "tenderly-v2" in networks.optimism.mainnet_fork.providers
    assert "tenderly-v2" in networks.base.mainnet_fork.providers


def test_test_provider_surface_on_the_wire(fake_rpc):
    from ape import accounts, networks

    with networks.parse_network_choice("ethereum:mainnet-fork:tenderly-v2",
                                       provider_settings={"uri": fake_rpc}) as p:
        assert p.name == "tenderly-v2" and p.chain_id == 1
        assert p.auto_mine is True
        snap = p.snapshot()
        assert p.unlock_account(MS) is True
        p.set_balance(MS, 10 ** 19)
        p.set_timestamp(1750074671)
        p.mine(3)
        p.set_code(MS, "6001")
        p.set_storage(MS, 0, 5)
        assert type(accounts[MS]).__name__ == "ImpersonatedAccount"
        assert p.restore(snap) is True
        p.relock_account(MS)
    assert wire() == ["evm_snapshot", "tenderly_setBalance", "evm_setNextBlockTimestamp",
                      "evm_increaseBlocks", "tenderly_setCode", "tenderly_setStorageAt",
                      "evm_revert"]
    assert ("evm_setNextBlockTimestamp", ["1750074671"]) in FakeAdminRpc.seen
    assert ("tenderly_setBalance", [MS, hex(10 ** 19)]) in FakeAdminRpc.seen
    assert ("evm_increaseBlocks", ["0x3"]) in FakeAdminRpc.seen


def test_tenderly_extras(fake_rpc):
    from ape import networks

    with networks.parse_network_choice("ethereum:mainnet-fork:tenderly-v2",
                                       provider_settings={"uri": fake_rpc}) as p:
        p.add_balance(MS, 5)
        p.set_erc20_balance(TOKEN, MS, 7)
        p.add_erc20_balance(TOKEN, MS, 8)
        p.deal_erc20(MS, TOKEN, 9)
        p.increase_time(60)
        p.increase_blocks(2)
        p.set_next_block_timestamp(1750074672)
    assert wire() == ["tenderly_addBalance", "tenderly_setErc20Balance",
                      "tenderly_addErc20Balance", "tenderly_setErc20Balance",
                      "evm_increaseTime", "evm_increaseBlocks",
                      "tenderly_setNextBlockTimestamp"]
    assert ("tenderly_setErc20Balance", [TOKEN, MS, "0x9"]) in FakeAdminRpc.seen
    assert ("tenderly_setNextBlockTimestamp", ["1750074672"]) in FakeAdminRpc.seen


def test_uri_resolution_order(fake_rpc, no_creds, isolated_records):
    from ape import networks
    from ape.exceptions import ProviderError
    from ape_tenderly_v2 import client as tc

    net = networks.ethereum.mainnet_fork
    with pytest.raises(ProviderError) as e:
        net.get_provider("tenderly-v2").uri
    assert "TENDERLY_ACCOUNT" in str(e.value)
    tc.save_records(isolated_records, {"ethereum:mainnet-fork": {"id": "v1", "admin_rpc": fake_rpc}})
    assert net.get_provider("tenderly-v2").uri == fake_rpc
    assert net.get_provider("tenderly-v2", provider_settings={"uri": "http://x"}).uri == "http://x"


def test_connect_creates_vnet_when_creds_exist(fake_rpc, monkeypatch, isolated_records):
    from ape import networks
    from ape_tenderly_v2 import client as tc

    monkeypatch.setenv("TENDERLY_ACCOUNT", "acct")
    monkeypatch.setenv("TENDERLY_PROJECT", "proj")
    monkeypatch.setenv("TENDERLY_ACCESS_KEY", "key")
    calls = []

    def fake_http(method, url, headers, body=None, timeout=60):
        calls.append((method, url, body))
        if method == "POST":
            return 200, {"id": "vnet-1", "rpcs": [{"name": "Admin RPC", "url": fake_rpc},
                                                  {"name": "Public RPC", "url": fake_rpc}],
                         "fork_config": {"network_id": 1, "block_number": 23000000}}
        return 204, {}

    monkeypatch.setattr(tc, "_http_json", fake_http)
    p = networks.ethereum.mainnet_fork.get_provider("tenderly-v2")
    p.connect()
    try:
        assert p.record["id"] == "vnet-1" and p.record["block"] == 23000000
        assert calls[0][2]["virtual_network_config"]["chain_config"]["chain_id"] == 1
        assert tc.load_records(isolated_records)["ethereum:mainnet-fork"]["id"] == "vnet-1"
        assert p.dashboard_url == "https://dashboard.tenderly.co/acct/proj/testnet/vnet-1"
        rec = p.restart()
        assert rec["id"] == "vnet-1"
        assert any(c[0] == "DELETE" for c in calls) is False  # same id: nothing deleted
    finally:
        p.disconnect()


def test_wrong_chain_on_gateway_refused(fake_rpc, monkeypatch, no_creds):
    from ape import networks
    from ape.exceptions import ProviderError

    FakeAdminRpc.chain_id = "0xa"  # optimism
    p = networks.ethereum.mainnet.get_provider("tenderly-v2", provider_settings={"uri": fake_rpc})
    with pytest.raises(ProviderError) as e:
        p.connect()
    assert "chain id 10" in str(e.value)
