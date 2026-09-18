"""``ape tenderly-v2 ...``: manage Virtual TestNets and run simulations from
the shell."""
from __future__ import annotations

import json
import os
from pathlib import Path

import click

from . import client as tc
from . import networks


def _creds() -> tc.Credentials:
    from ape import config

    settings = config.get_config("tenderly-v2")
    creds = tc.Credentials.resolve(getattr(settings, "account", None),
                                   getattr(settings, "project", None),
                                   getattr(settings, "access_key", None))
    if creds is None:
        raise click.ClickException(
            "set TENDERLY_ACCOUNT, TENDERLY_PROJECT and TENDERLY_ACCESS_KEY (env or "
            "tenderly-v2 config)")
    return creds


def _records_path() -> Path:
    from ape import config

    return Path(config.DATA_FOLDER) / "tenderly_v2" / "vnets.json"


@click.group()
def cli():
    """Tenderly Virtual TestNets, Node RPC and simulations."""


@cli.group()
def vnets():
    """Create, list, inspect and delete Virtual TestNets."""


@vnets.command("list")
@click.option("--json", "as_json", is_flag=True, help="raw API output")
def vnets_list(as_json):
    """Virtual TestNets in the project, with the ones this machine recorded marked."""
    client = tc.TenderlyClient(_creds())
    items = client.list_vnets()
    if as_json:
        click.echo(json.dumps(items, indent=1))
        return
    recorded = {r.get("id") for r in tc.load_records(_records_path()).values()}
    for v in items:
        vid = v.get("id")
        fork = v.get("fork_config") or {}
        mark = "*" if vid in recorded else " "
        click.echo(f"{mark} {vid}  {v.get('slug', ''):32s} network {fork.get('network_id')}"
                   f" @ {fork.get('block_number')}")
    click.echo("\n* = recorded in " + str(_records_path()))


@vnets.command("create")
@click.option("--ecosystem", default="ethereum", show_default=True)
@click.option("--network", default="mainnet", show_default=True)
@click.option("--block", default="latest", show_default=True)
@click.option("--chain-id", type=int, default=None, help="custom chain id (default: real)")
@click.option("--sync-state", is_flag=True)
@click.option("--explorer", is_flag=True, help="enable the public explorer page")
@click.option("--label", default="ape", show_default=True)
@click.option("--record/--no-record", default=True,
              help="record it as the vnet the tenderly-v2 provider uses for this network")
def vnets_create(ecosystem, network, block, chain_id, sync_state, explorer, label, record):
    """Create a Virtual TestNet forking ECOSYSTEM:NETWORK."""
    try:
        network_id = networks.chain_id(ecosystem, network)
    except KeyError as e:
        raise click.ClickException(str(e))
    client = tc.TenderlyClient(_creds())
    blk: str | int = block if block == "latest" else int(block)
    try:
        rec = client.create_vnet(network_id=network_id, chain_id=chain_id, block=blk,
                                 sync_state=sync_state, explorer=explorer, label=label)
    except tc.TenderlyClientError as e:
        raise click.ClickException(str(e))
    if record:
        path = _records_path()
        records = tc.load_records(path)
        records[f"{ecosystem}:{network}-fork"] = rec
        tc.save_records(path, records)
    click.echo(json.dumps({**rec, "dashboard": client.vnet_url(rec["id"])}, indent=1))


@vnets.command("show")
@click.argument("vnet_id")
def vnets_show(vnet_id):
    """Raw API record of one Virtual TestNet."""
    click.echo(json.dumps(tc.TenderlyClient(_creds()).get_vnet(vnet_id), indent=1))


@vnets.command("rpc")
@click.option("--ecosystem", default="ethereum", show_default=True)
@click.option("--network", default="mainnet", show_default=True)
@click.option("--public", is_flag=True, help="print the Public RPC instead of the Admin RPC")
def vnets_rpc(ecosystem, network, public):
    """Print the recorded vnet's RPC url for ECOSYSTEM:NETWORK-fork."""
    rec = tc.load_records(_records_path()).get(f"{ecosystem}:{network}-fork")
    if not rec:
        raise click.ClickException(f"no recorded vnet for {ecosystem}:{network}-fork")
    click.echo(rec["public_rpc" if public else "admin_rpc"])


@vnets.command("delete")
@click.argument("vnet_id")
def vnets_delete(vnet_id):
    """Delete a Virtual TestNet and forget it locally."""
    client = tc.TenderlyClient(_creds())
    if not client.delete_vnet(vnet_id):
        raise click.ClickException(f"delete failed for {vnet_id}")
    path = _records_path()
    records = tc.load_records(path)
    for key in [k for k, v in records.items() if v.get("id") == vnet_id]:
        records.pop(key)
    tc.save_records(path, records)
    click.echo(f"deleted {vnet_id}")


@vnets.command("prune")
@click.option("--keep-recorded/--no-keep-recorded", default=True,
              help="never delete the vnets this machine recorded")
@click.option("--label", default=None, help="only vnets whose slug starts with LABEL")
@click.option("--yes", is_flag=True, help="do not ask")
def vnets_prune(keep_recorded, label, yes):
    """Delete project vnets in bulk (by slug prefix), keeping the recorded ones."""
    client = tc.TenderlyClient(_creds())
    recorded = {r.get("id") for r in tc.load_records(_records_path()).values()}
    victims = [v for v in client.list_vnets()
               if (not label or str(v.get("slug", "")).startswith(label))
               and not (keep_recorded and v.get("id") in recorded)]
    if not victims:
        click.echo("nothing to prune")
        return
    for v in victims:
        click.echo(f"  {v.get('id')}  {v.get('slug')}")
    if not yes and not click.confirm(f"delete {len(victims)} vnet(s)?"):
        return
    n = sum(1 for v in victims if client.delete_vnet(v["id"]))
    click.echo(f"deleted {n}/{len(victims)}")


@cli.command()
@click.option("--ecosystem", default="ethereum", show_default=True)
@click.option("--network", default="mainnet", show_default=True)
@click.option("--from", "from_", required=True, help="sender (no signature needed)")
@click.option("--to", required=True)
@click.option("--input", "input_", default="0x", show_default=True, help="calldata hex")
@click.option("--value", default="0", show_default=True, help="wei")
@click.option("--gas", default=8_000_000, show_default=True)
@click.option("--block", type=int, default=None, help="simulate at this block (default: head)")
@click.option("--json", "as_json", is_flag=True, help="raw API output")
def simulate(ecosystem, network, from_, to, input_, value, gas, block, as_json):
    """Simulate one transaction on the live chain through the Simulation API."""
    try:
        network_id = networks.chain_id(ecosystem, network)
    except KeyError as e:
        raise click.ClickException(str(e))
    client = tc.TenderlyClient(_creds())
    try:
        res = client.simulate(network_id=network_id, from_=from_, to=to, input=input_,
                              value=int(value), gas=int(gas), block_number=block)
    except tc.TenderlyClientError as e:
        raise click.ClickException(str(e))
    if as_json:
        click.echo(json.dumps(res, indent=1))
        return
    s = client.simulation_summary(res)
    click.echo(f"status   {'ok' if s['status'] else 'REVERTED'}")
    click.echo(f"gas used {s['gas_used']}")
    if s["error"]:
        click.echo(f"error    {s['error']}")
    for ch in s["asset_changes"]:
        tok = (ch.get("token_info") or {}).get("symbol", "?")
        click.echo(f"  {ch.get('type', ''):8s} {ch.get('amount', ch.get('raw_amount'))} {tok} "
                   f"{ch.get('from', '')[:10]} -> {ch.get('to', '')[:10]}")
    if s["url"]:
        click.echo(f"url      {s['url']}")


@cli.command("gateway-url")
@click.option("--ecosystem", default="ethereum", show_default=True)
@click.option("--network", default="mainnet", show_default=True)
def gateway_url(ecosystem, network):
    """Print the Tenderly Node RPC url the gateway provider would use."""
    key = os.environ.get("TENDERLY_GATEWAY_ACCESS_KEY")
    click.echo(networks.gateway_url(ecosystem, network, key))
