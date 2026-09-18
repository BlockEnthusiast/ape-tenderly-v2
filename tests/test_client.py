import pytest

from ape_tenderly_v2 import client as tc
from ape_tenderly_v2 import networks


def _client(monkeypatch, responder):
    monkeypatch.setattr(tc, "_http_json", responder)
    return tc.TenderlyClient(tc.Credentials("acct", "proj", "key"))


def test_credentials_env_first(monkeypatch):
    for v in ("TENDERLY_ACCOUNT", "TENDERLY_PROJECT", "TENDERLY_ACCESS_KEY"):
        monkeypatch.delenv(v, raising=False)
    assert tc.Credentials.resolve() is None
    assert tc.Credentials.resolve("a", "p", "k").project_url.endswith("/account/a/project/p")
    monkeypatch.setenv("TENDERLY_ACCOUNT", "env")
    assert tc.Credentials.resolve("a", "p", "k").account == "env"


def test_create_vnet_and_delete(monkeypatch):
    calls = []

    def fake(method, url, headers, body=None, timeout=60):
        calls.append((method, url, headers, body))
        if method == "POST":
            return 200, {"id": "vnet-new", "rpcs": [
                {"name": "Admin RPC", "url": "https://virtual.mainnet.rpc.tenderly.co/adminNEW"},
                {"name": "Public RPC", "url": "https://virtual.mainnet.rpc.tenderly.co/pubNEW"}],
                "fork_config": {"network_id": 1, "block_number": 23000000}}
        return 204, {}

    c = _client(monkeypatch, fake)
    rec = c.create_vnet(network_id=1, chain_id=73571, block=22_000_000, sync_state=True,
                        explorer=True, label="t")
    assert rec["admin_rpc"].endswith("adminNEW") and rec["public_rpc"].endswith("pubNEW")
    assert rec["chain_id"] == 73571 and rec["block"] == 23000000
    method, url, headers, body = calls[0]
    assert method == "POST" and url == "https://api.tenderly.co/api/v1/account/acct/project/proj/vnets"
    assert headers["X-Access-Key"] == "key"
    assert body["fork_config"] == {"network_id": 1, "block_number": 22_000_000}
    assert body["virtual_network_config"]["chain_config"]["chain_id"] == 73571
    assert body["sync_state_config"]["enabled"] is True
    assert body["explorer_page_config"]["enabled"] is True
    assert c.delete_vnet("vnet-old") is True
    assert calls[1][0] == "DELETE" and calls[1][1].endswith("/vnets/vnet-old")


def test_create_vnet_http_failure(monkeypatch):
    c = _client(monkeypatch, lambda *a, **k: (401, {"error": "bad key"}))
    with pytest.raises(tc.TenderlyClientError) as e:
        c.create_vnet(network_id=1)
    assert e.value.status == 401 and "HTTP 401" in str(e.value)
    assert c.delete_vnet("x") is False


def test_list_vnets_shapes(monkeypatch):
    c = _client(monkeypatch, lambda *a, **k: (200, [{"id": "a"}]))
    assert c.list_vnets() == [{"id": "a"}]
    c = _client(monkeypatch, lambda *a, **k: (200, {"vnets": [{"id": "b"}]}))
    assert c.list_vnets() == [{"id": "b"}]


def test_simulate_and_bundle(monkeypatch):
    calls = []

    def fake(method, url, headers, body=None, timeout=60):
        calls.append((method, url, body))
        if url.endswith("/simulate"):
            return 200, {"transaction": {"status": True, "gas_used": 21000,
                                         "transaction_info": {"asset_changes": [{"type": "Transfer"}]}},
                         "simulation": {"id": "sim-1", "status": True}}
        return 200, {"simulation_results": [{"simulation": {"id": "s1", "status": True}},
                                            {"simulation": {"id": "s2", "status": False}}]}

    c = _client(monkeypatch, fake)
    res = c.simulate(network_id=1, from_="0xa", to="0xb", input="0x1234", block_number=100)
    body = calls[0][2]
    assert body["network_id"] == "1" and body["block_number"] == 100 and body["save"] is True
    assert body["from"] == "0xa" and body["input"] == "0x1234" and body["gas"] == 8_000_000
    s = tc.TenderlyClient.simulation_summary(res)
    assert s["status"] and s["gas_used"] == 21000 and s["asset_changes"] == [{"type": "Transfer"}]
    assert s["url"] == "https://dashboard.tenderly.co/shared/simulation/sim-1"
    results = c.simulate_bundle(network_id=10, transactions=[
        {"from": "0xa", "to": "0xb"}, {"from": "0xa", "to": "0xc", "input": "0x99", "value": 5}])
    assert [r["simulation"]["id"] for r in results] == ["s1", "s2"]
    sims = calls[1][2]["simulations"]
    assert len(sims) == 2 and sims[1]["value"] == "5" and sims[0]["network_id"] == "10"


def test_urls():
    c = tc.TenderlyClient(tc.Credentials("acct", "proj", "key"))
    assert c.vnet_url("v") == "https://dashboard.tenderly.co/acct/proj/testnet/v"
    assert c.vnet_transaction_url("v", "0xh") == "https://dashboard.tenderly.co/acct/proj/testnet/v/tx/0xh"
    assert c.simulation_url("s") == "https://dashboard.tenderly.co/acct/proj/simulator/s"
    assert tc.TenderlyClient.public_transaction_url("mainnet", "0xh") == "https://dashboard.tenderly.co/tx/mainnet/0xh"
    assert tc.TenderlyClient.public_contract_url("base", "0xa") == "https://dashboard.tenderly.co/contract/base/0xa"
    assert tc.TenderlyClient.shared_simulation_url(None) is None


def test_records_and_redact(tmp_path):
    path = tmp_path / "vnets.json"
    tc.save_records(path, {"ethereum:mainnet-fork": {"id": "v"}})
    assert tc.load_records(path)["ethereum:mainnet-fork"]["id"] == "v"
    assert tc.load_records(tmp_path / "missing.json") == {}
    assert tc.redact("https://virtual.mainnet.rpc.tenderly.co/abc123def456").endswith("…def456")
    assert "abc123" not in tc.redact("https://virtual.mainnet.rpc.tenderly.co/abc123def456")
    assert tc.redact("http://127.0.0.1:8551") == "http://127.0.0.1:8551"
    assert tc.redact(None) is None


def test_networks_table():
    assert networks.chain_id("ethereum", "mainnet-fork") == 1
    assert networks.chain_id("base", "mainnet") == 8453
    assert networks.gateway_slug("ethereum", "mainnet") == "mainnet"
    assert networks.gateway_slug("ethereum", "sepolia") == "sepolia"
    assert networks.gateway_slug("optimism", "mainnet") == "optimism"
    assert networks.gateway_slug("base", "sepolia") == "base-sepolia"
    assert networks.gateway_slug("polygon", "amoy") == "polygon-amoy"
    assert networks.gateway_slug("fantom", "opera") == "fantom"
    assert networks.gateway_url("arbitrum", "mainnet", "KEY") == "https://arbitrum.gateway.tenderly.co/KEY"
    assert networks.gateway_url("arbitrum", "mainnet") == "https://arbitrum.gateway.tenderly.co"
    with pytest.raises(KeyError):
        networks.chain_id("ethereum", "goerli")
    assert ("ethereum", "mainnet-fork") in set(networks.fork_networks())
