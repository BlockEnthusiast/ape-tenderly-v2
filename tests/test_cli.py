import json

from click.testing import CliRunner

from ape_tenderly_v2 import client as tc
from ape_tenderly_v2._cli import cli


def _env(monkeypatch):
    monkeypatch.setenv("TENDERLY_ACCOUNT", "acct")
    monkeypatch.setenv("TENDERLY_PROJECT", "proj")
    monkeypatch.setenv("TENDERLY_ACCESS_KEY", "key")


def test_help_lists_commands():
    r = CliRunner().invoke(cli, ["--help"])
    assert r.exit_code == 0
    for cmd in ("vnets", "simulate", "gateway-url"):
        assert cmd in r.output


def test_missing_creds(monkeypatch, no_creds):
    r = CliRunner().invoke(cli, ["vnets", "list"])
    assert r.exit_code != 0 and "TENDERLY_ACCOUNT" in r.output


def test_vnets_create_list_delete(monkeypatch, tmp_path):
    _env(monkeypatch)
    import ape_tenderly_v2._cli as m
    monkeypatch.setattr(m, "_records_path", lambda: tmp_path / "vnets.json")
    store = {}

    def fake(method, url, headers, body=None, timeout=60):
        if method == "POST":
            store["v1"] = {"id": "v1", "slug": body["slug"], "fork_config": body["fork_config"]}
            return 200, {"id": "v1", "rpcs": [{"name": "Admin RPC", "url": "https://a/x"},
                                              {"name": "Public RPC", "url": "https://p/x"}],
                         "fork_config": {"network_id": 8453, "block_number": 5}}
        if method == "GET":
            return 200, list(store.values())
        store.pop(url.rsplit("/", 1)[-1], None)
        return 204, {}

    monkeypatch.setattr(tc, "_http_json", fake)
    r = CliRunner().invoke(cli, ["vnets", "create", "--ecosystem", "base", "--network", "mainnet",
                                 "--label", "cli"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["admin_rpc"] == "https://a/x" and out["dashboard"].endswith("/testnet/v1")
    assert tc.load_records(tmp_path / "vnets.json")["base:mainnet-fork"]["id"] == "v1"

    r = CliRunner().invoke(cli, ["vnets", "list"])
    assert r.exit_code == 0 and "* v1" in r.output and "network 8453" in r.output

    r = CliRunner().invoke(cli, ["vnets", "rpc", "--ecosystem", "base", "--network", "mainnet", "--public"])
    assert r.exit_code == 0 and r.output.strip() == "https://p/x"

    r = CliRunner().invoke(cli, ["vnets", "delete", "v1"])
    assert r.exit_code == 0 and "deleted v1" in r.output
    assert tc.load_records(tmp_path / "vnets.json") == {}


def test_simulate_summary(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setattr(tc, "_http_json", lambda *a, **k: (200, {
        "transaction": {"status": False, "gas_used": 30000, "error_message": "boom",
                        "transaction_info": {"asset_changes": [
                            {"type": "Transfer", "amount": "1.5", "from": "0xaaaa", "to": "0xbbbb",
                             "token_info": {"symbol": "WETH"}}]}},
        "simulation": {"id": "s1", "status": False}}))
    r = CliRunner().invoke(cli, ["simulate", "--from", "0xa", "--to", "0xb", "--input", "0x12"])
    assert r.exit_code == 0, r.output
    assert "REVERTED" in r.output and "boom" in r.output and "WETH" in r.output
    assert "shared/simulation/s1" in r.output


def test_gateway_url(monkeypatch, no_creds):
    r = CliRunner().invoke(cli, ["gateway-url", "--ecosystem", "base", "--network", "sepolia"])
    assert r.exit_code == 0 and r.output.strip() == "https://base-sepolia.gateway.tenderly.co"
