import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

MS = "0xF56D660138815fC5d7a06cd0E1630225E788293D"
TOKEN = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

_BLOCK = {"number": "0x10", "timestamp": hex(1_700_000_000), "hash": "0x" + "11" * 32,
          "parentHash": "0x" + "00" * 32, "gasLimit": "0x1c9c380", "gasUsed": "0x0",
          "baseFeePerGas": "0x1", "transactions": [], "size": "0x1", "difficulty": "0x0",
          "totalDifficulty": "0x0", "miner": "0x" + "00" * 20, "nonce": "0x0000000000000000",
          "extraData": "0x", "logsBloom": "0x" + "00" * 256, "sha3Uncles": "0x" + "00" * 32,
          "stateRoot": "0x" + "00" * 32, "receiptsRoot": "0x" + "00" * 32,
          "transactionsRoot": "0x" + "00" * 32, "uncles": []}

_OK = {"evm_revert", "tenderly_setBalance", "tenderly_addBalance", "tenderly_setCode",
       "tenderly_setStorageAt", "tenderly_setErc20Balance", "tenderly_addErc20Balance"}
_HASH = {"evm_increaseBlocks", "evm_increaseTime", "evm_setNextBlockTimestamp",
         "tenderly_setNextBlockTimestamp"}


class FakeAdminRpc(BaseHTTPRequestHandler):
    """Answers like a Tenderly Admin RPC and records every method."""
    seen: list = []
    chain_id = "0x1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        reqs = body if isinstance(body, list) else [body]
        outs = []
        for b in reqs:
            m, p = b["method"], b.get("params", [])
            type(self).seen.append((m, p))
            r = {"jsonrpc": "2.0", "id": b["id"]}
            if m == "eth_chainId":
                r["result"] = type(self).chain_id
            elif m == "web3_clientVersion":
                r["result"] = "tenderly/fake"
            elif m == "eth_getBlockByNumber":
                r["result"] = _BLOCK
            elif m == "eth_blockNumber":
                r["result"] = "0x10"
            elif m == "eth_gasPrice":
                r["result"] = "0x1"
            elif m == "evm_snapshot":
                r["result"] = "0x" + "ab" * 32
            elif m in _OK:
                r["result"] = True
            elif m in _HASH:
                r["result"] = "0x" + "cd" * 32
            elif m == "eth_getBalance":
                r["result"] = hex(10 ** 19)
            else:
                r["error"] = {"code": -32601, "message": f"unknown {m}"}
            outs.append(r)
        out = json.dumps(outs if isinstance(body, list) else outs[0]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


@pytest.fixture
def fake_rpc():
    FakeAdminRpc.seen = []
    FakeAdminRpc.chain_id = "0x1"
    srv = HTTPServer(("127.0.0.1", 0), FakeAdminRpc)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def no_creds(monkeypatch):
    for v in ("TENDERLY_ACCOUNT", "TENDERLY_PROJECT", "TENDERLY_ACCESS_KEY",
              "TENDERLY_GATEWAY_ACCESS_KEY"):
        monkeypatch.delenv(v, raising=False)


@pytest.fixture
def isolated_records(monkeypatch, tmp_path):
    import ape_tenderly_v2.vnet_provider as prov

    path = tmp_path / "vnets.json"
    monkeypatch.setattr(prov.TenderlyVnetProvider, "records_path", property(lambda self: path))
    return path


def wire():
    return [m for m, _ in FakeAdminRpc.seen if not m.startswith(("eth_chainId", "web3_"))]
