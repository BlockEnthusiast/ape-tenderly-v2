"""Tenderly REST client: Virtual TestNets, the Simulation API, contract
verification, dashboard urls, and the local record of vnets this machine
created.

Shapes follow Tenderly's own tooling (``Tenderly/vnet-github-action``,
``src/tenderly.ts``) and API docs:

    POST   {API}/account/{a}/project/{p}/vnets            -> {id, slug, rpcs:[{name,url}], fork_config}
    GET    {API}/account/{a}/project/{p}/vnets
    GET    {API}/account/{a}/project/{p}/vnets/{id}
    DELETE {API}/account/{a}/project/{p}/vnets/{id}
    POST   {API}/account/{a}/project/{p}/simulate         -> {transaction, simulation, contracts...}
    POST   {API}/account/{a}/project/{p}/simulate-bundle  -> {simulation_results:[...]}
    POST   {API}/account/{a}/project/{p}/contracts        -> verification (experimental)

Only ``urllib`` is used, so the plugin adds no HTTP dependency.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

API = "https://api.tenderly.co/api/v1"
DASHBOARD = "https://dashboard.tenderly.co"


class TenderlyClientError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass(frozen=True)
class Credentials:
    account: str
    project: str
    access_key: str

    @classmethod
    def resolve(cls, account: str | None = None, project: str | None = None,
                access_key: str | None = None) -> "Credentials | None":
        """Environment first, then the given (config) values."""
        a = os.environ.get("TENDERLY_ACCOUNT") or account
        p = os.environ.get("TENDERLY_PROJECT") or project
        k = os.environ.get("TENDERLY_ACCESS_KEY") or access_key
        if not (a and p and k):
            return None
        return cls(a, p, k)

    @property
    def project_url(self) -> str:
        return f"{API}/account/{self.account}/project/{self.project}"

    @property
    def headers(self) -> dict:
        return {"X-Access-Key": self.access_key,
                "Content-Type": "application/json",
                "Accept": "application/json"}


def _http_json(method: str, url: str, headers: dict, body: dict | None = None,
               timeout: int = 60) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data, headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except ValueError:
            return e.code, {"error": e.reason}


class TenderlyClient:
    def __init__(self, creds: Credentials, timeout: int = 60):
        self.creds = creds
        self.timeout = timeout

    # ---------------------------------------------------------------- http

    def _call(self, method: str, path: str, body: dict | None = None,
              ok: tuple[int, ...] = (200, 201, 204)) -> Any:
        url = path if path.startswith("http") else f"{self.creds.project_url}{path}"
        status, res = _http_json(method, url, self.creds.headers, body, self.timeout)
        if status not in ok:
            raise TenderlyClientError(
                f"{method} {path}: HTTP {status} {json.dumps(res)[:300]}", status, res)
        return res

    # ---------------------------------------------------------------- vnets

    def list_vnets(self) -> list[dict]:
        res = self._call("GET", "/vnets")
        return res if isinstance(res, list) else res.get("vnets", res.get("items", []))

    def get_vnet(self, vnet_id: str) -> dict:
        return self._call("GET", f"/vnets/{vnet_id}")

    def create_vnet(self, *, network_id: int, chain_id: int | None = None,
                    block: str | int = "latest", sync_state: bool = False,
                    explorer: bool = False, label: str = "ape",
                    display_name: str | None = None) -> dict:
        """Create a Virtual TestNet and return a normalised record::

            {id, slug, admin_rpc, public_rpc, network_id, chain_id, block, created}
        """
        slug = f"{label}-{network_id}-{int(time.time())}".lower()
        body = {
            "slug": slug,
            "display_name": display_name or f"{label} fork of network {network_id}",
            "fork_config": {"network_id": network_id, "block_number": block},
            "virtual_network_config": {"chain_config": {"chain_id": chain_id or network_id}},
            "sync_state_config": {"enabled": bool(sync_state), "commitment_level": "latest"},
            "explorer_page_config": {"enabled": bool(explorer),
                                     "verification_visibility": "bytecode"},
        }
        res = self._call("POST", "/vnets", body)
        if not isinstance(res.get("rpcs"), list):
            raise TenderlyClientError(f"vnet create returned no rpcs: {json.dumps(res)[:300]}")
        rpcs = {r.get("name"): r.get("url") for r in res["rpcs"]}
        if not rpcs.get("Admin RPC"):
            raise TenderlyClientError(f"vnet {slug} has no Admin RPC: {res['rpcs']}")
        return {
            "id": res.get("id"), "slug": slug,
            "admin_rpc": rpcs["Admin RPC"], "public_rpc": rpcs.get("Public RPC"),
            "network_id": network_id, "chain_id": chain_id or network_id,
            "block": (res.get("fork_config") or {}).get("block_number", block),
            "created": int(time.time()),
        }

    def delete_vnet(self, vnet_id: str) -> bool:
        try:
            self._call("DELETE", f"/vnets/{vnet_id}")
            return True
        except TenderlyClientError:
            return False

    # ---------------------------------------------------------------- simulation

    def simulate(self, *, network_id: int, from_: str, to: str, input: str = "0x",
                 value: int = 0, gas: int = 8_000_000, block_number: int | None = None,
                 save: bool = True, save_if_fails: bool = True,
                 simulation_type: str = "full",
                 state_objects: dict | None = None) -> dict:
        """One stateless simulation on the live chain state (or a block).
        Returns Tenderly's raw result (``transaction``, ``simulation`` ...)."""
        body = self._sim_body(network_id, from_, to, input, value, gas, block_number,
                              save, save_if_fails, simulation_type, state_objects)
        return self._call("POST", "/simulate", body)

    def simulate_bundle(self, *, network_id: int, transactions: list[dict],
                        block_number: int | None = None, save: bool = True,
                        save_if_fails: bool = True, simulation_type: str = "full") -> list[dict]:
        """Sequential simulations sharing state. Each item: ``{from, to, input,
        value?, gas?, state_objects?}``. Returns ``simulation_results``."""
        sims = [self._sim_body(network_id, t["from"], t["to"], t.get("input", "0x"),
                               int(t.get("value", 0)), int(t.get("gas", 8_000_000)),
                               block_number, save, save_if_fails, simulation_type,
                               t.get("state_objects"))
                for t in transactions]
        res = self._call("POST", "/simulate-bundle", {"simulations": sims})
        return res.get("simulation_results", [])

    @staticmethod
    def _sim_body(network_id, from_, to, input, value, gas, block_number, save,
                  save_if_fails, simulation_type, state_objects) -> dict:
        body: dict = {
            "network_id": str(network_id), "from": from_, "to": to, "input": input,
            "value": str(int(value)), "gas": int(gas), "gas_price": "0",
            "save": bool(save), "save_if_fails": bool(save_if_fails),
            "simulation_type": simulation_type,
        }
        if block_number is not None:
            body["block_number"] = int(block_number)
        if state_objects:
            body["state_objects"] = state_objects
        return body

    @staticmethod
    def simulation_summary(result: dict) -> dict:
        """Compact view of one simulation result: status, gas, error, url,
        and asset changes (token transfers Tenderly decoded)."""
        sim = result.get("simulation") or {}
        tx = result.get("transaction") or {}
        info = tx.get("transaction_info") or {}
        return {
            "id": sim.get("id"),
            "status": bool(sim.get("status", tx.get("status"))),
            "gas_used": tx.get("gas_used") or sim.get("gas_used"),
            "error": tx.get("error_message") or sim.get("error_message"),
            "url": TenderlyClient.shared_simulation_url(sim.get("id")),
            "asset_changes": info.get("asset_changes") or result.get("asset_changes") or [],
            "logs": info.get("logs") or [],
        }

    # ---------------------------------------------------------------- verification (experimental)

    def verify_contract(self, *, network_id: int, address: str, contract_name: str,
                        sources: dict[str, str], compiler_version: str,
                        optimizer_enabled: bool = False, optimizer_runs: int = 200,
                        evm_version: str | None = None, public: bool = False) -> Any:
        """Verify a contract in the project (private) or publicly.

        Experimental: the payload follows Tenderly's documented contract
        verification request. Check the response before relying on it."""
        body = {
            "config": {"optimizations_used": bool(optimizer_enabled),
                       "optimizations_count": int(optimizer_runs),
                       **({"evm_version": evm_version} if evm_version else {})},
            "contracts": [{
                "contractName": contract_name,
                "source": sources.get(contract_name + ".sol") or next(iter(sources.values())),
                "sourcePath": next(iter(sources.keys())),
                "networks": {str(network_id): {"address": address}},
                "compiler": {"name": "solc", "version": compiler_version},
            }],
        }
        path = "/contracts" if not public else f"{API}/account/{self.creds.account}/project/{self.creds.project}/contracts/verify-public"
        return self._call("POST", path, body, ok=(200, 201))

    # ---------------------------------------------------------------- urls

    def vnet_url(self, vnet_id: str) -> str:
        return f"{DASHBOARD}/{self.creds.account}/{self.creds.project}/testnet/{vnet_id}"

    def vnet_transaction_url(self, vnet_id: str, tx_hash: str) -> str:
        return f"{self.vnet_url(vnet_id)}/tx/{tx_hash}"

    def simulation_url(self, sim_id: str) -> str:
        return f"{DASHBOARD}/{self.creds.account}/{self.creds.project}/simulator/{sim_id}"

    @staticmethod
    def shared_simulation_url(sim_id: str | None) -> str | None:
        return f"{DASHBOARD}/shared/simulation/{sim_id}" if sim_id else None

    @staticmethod
    def public_transaction_url(gateway_slug: str, tx_hash: str) -> str:
        return f"{DASHBOARD}/tx/{gateway_slug}/{tx_hash}"

    @staticmethod
    def public_contract_url(gateway_slug: str, address: str) -> str:
        return f"{DASHBOARD}/contract/{gateway_slug}/{address}"

    @staticmethod
    def public_contract(network_id: int, address: str, timeout: int = 30) -> Optional[dict]:
        """Tenderly's public contract endpoint (ABI, name, source when verified).
        Returns None when unknown or unreachable."""
        status, res = _http_json(
            "GET", f"{API}/public-contract/{network_id}/{address}",
            {"Accept": "application/json"}, timeout=timeout)
        return res if status == 200 and isinstance(res, dict) else None


# -------------------------------------------------------------------- records

def load_records(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_records(path: Path, records: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(records, indent=1))
    tmp.replace(path)


def redact(url: str | None) -> str | None:
    """Admin RPC and gateway urls embed a secret path segment; keep host + tail."""
    if not url or "tenderly" not in url:
        return url
    head, _, tail = url.rpartition("/")
    return f"{head}/…{tail[-6:]}" if len(tail) > 8 else url
