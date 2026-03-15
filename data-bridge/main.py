"""AEGIS Data Bridge — orchestrates all collectors for configured environments."""

import asyncio
import os
import sys

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

# Load .env from project root
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_project_root, ".env"))

# Add project root to path for config access
sys.path.insert(0, os.path.join(_project_root, "orion-hub"))

from collectors.wazuh import WazuhCollector
from collectors.winrm import WinRMCollector
from collectors.ping import PingCollector
from collectors.vpn_check import VPNCheckCollector
from collectors.unifi import UniFiCollector
from collectors.powershell_api import PowerShellAPICollector

# ---------------------------------------------------------------------------
# Environment configuration helpers
# ---------------------------------------------------------------------------


def _get_env_config(env_name: str) -> dict:
    """Get configuration for a specific environment from env vars."""
    prefix = f"ENV_{env_name}_"
    config = {}
    for key, value in os.environ.items():
        if key.startswith(prefix) and value:
            short_key = key[len(prefix):].lower()
            config[short_key] = value
    return config


def _get_ping_targets() -> dict[str, dict[str, str]]:
    """Build ping targets from environment variables.

    Returns: {env_name: {hostname: ip_address}}
    """
    targets: dict[str, dict[str, str]] = {}

    # PERSONAL environment hosts
    personal_hosts = {}
    for suffix, name in [
        ("CRYPTOEDGE_HOST", "CryptoEdge"),
        ("MBG6_HOST", "MBG6"),
        ("NEUROGENISYS_HOST", "Neurogenisys"),
    ]:
        ip = os.getenv(f"ENV_PERSONAL_{suffix}", "")
        if ip:
            personal_hosts[name] = ip
    if personal_hosts:
        targets["PERSONAL"] = personal_hosts

    # CEDERVALL — servers from env vars
    cedervall_hosts = {}
    server_map = {
        "DC_PRIMARY": "CV-DC05",
        "DC_SECONDARY": "CV-DC06",
        "FS01": "CV-FS01",
        "FS05": "CV-FS05",
        "APP01": "CV-APP1",
        "JUMP": "CV-NSS001",
    }
    for suffix, name in server_map.items():
        ip = os.getenv(f"ENV_CEDERVALL_{suffix}", "")
        if ip:
            cedervall_hosts[name] = ip
    # Also add UniFi gateway
    unifi_url = os.getenv("ENV_CEDERVALL_UNIFI_URL", "")
    if unifi_url:
        ip = unifi_url.replace("https://", "").replace("http://", "").split(":")[0].split("/")[0]
        if ip:
            cedervall_hosts["UniFi-GW"] = ip
    if cedervall_hosts:
        targets["CEDERVALL"] = cedervall_hosts

    # VALVX — WinRM host
    valvx_host = os.getenv("ENV_VALVX_WINRM_HOST", "")
    if valvx_host:
        targets["VALVX"] = {"VX-DC": valvx_host}

    # GWSK — WinRM host
    gwsk_host = os.getenv("ENV_GWSK_WINRM_HOST", "")
    if gwsk_host:
        targets["GWSK"] = {"GW-DC": gwsk_host}

    return targets


# ---------------------------------------------------------------------------
# Task wrapper with auto-restart
# ---------------------------------------------------------------------------


async def _supervised_task(name: str, coro_factory) -> None:
    """Run a collector coroutine with auto-restart on crash.

    Args:
        name: Human-readable name for logging.
        coro_factory: Callable that returns a coroutine (the collector's run method).
    """
    while True:
        try:
            print(f"[BRIDGE] Starting {name}")
            await coro_factory()
        except asyncio.CancelledError:
            print(f"[BRIDGE] {name} cancelled")
            break
        except Exception as exc:
            print(f"[BRIDGE] {name} crashed: {exc}")
            print(f"[BRIDGE] Restarting {name} in 10s...")
            await asyncio.sleep(10)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    """Start all configured collectors as supervised asyncio tasks."""
    tasks: list[asyncio.Task] = []
    collectors = []

    print("[BRIDGE] ========================================")
    print("[BRIDGE] AEGIS Data Bridge starting")
    print("[BRIDGE] ========================================")

    # ---- PowerShell API collector (Cedervall) ----
    cedervall_config = _get_env_config("CEDERVALL")
    if cedervall_config.get("jump_url") and cedervall_config.get("jump_api_key"):
        collector = PowerShellAPICollector(cedervall_config)
        collectors.append(collector)
        tasks.append(
            asyncio.create_task(
                _supervised_task("PS-API/CEDERVALL", collector.run)
            )
        )
    else:
        print("[BRIDGE] PS-API/CEDERVALL — skipped (no jump_url or jump_api_key)")

    # ---- Wazuh collectors ----
    for env_name in ("CEDERVALL", "VALVX"):
        config = _get_env_config(env_name)
        if config.get("wazuh_url") and config.get("wazuh_user"):
            collector = WazuhCollector(env_name, config)
            collectors.append(collector)
            tasks.append(
                asyncio.create_task(
                    _supervised_task(f"Wazuh/{env_name}", collector.run)
                )
            )
        else:
            print(f"[BRIDGE] Wazuh/{env_name} — skipped (not configured)")

    # ---- WinRM collectors ----
    for env_name in ("CEDERVALL", "VALVX", "GWSK"):
        config = _get_env_config(env_name)
        if config.get("winrm_host") and config.get("winrm_user"):
            collector = WinRMCollector(env_name, config)
            collectors.append(collector)
            tasks.append(
                asyncio.create_task(
                    _supervised_task(f"WinRM/{env_name}", collector.run)
                )
            )
        else:
            print(f"[BRIDGE] WinRM/{env_name} — skipped (not configured)")

    # ---- UniFi collector ----
    for env_name in ("CEDERVALL",):
        config = _get_env_config(env_name)
        if config.get("unifi_url") and config.get("unifi_key"):
            collector = UniFiCollector(env_name, config)
            collectors.append(collector)
            tasks.append(
                asyncio.create_task(
                    _supervised_task(f"UniFi/{env_name}", collector.run)
                )
            )
        else:
            print(f"[BRIDGE] UniFi/{env_name} — skipped (not configured)")

    # ---- Ping collectors ----
    ping_targets = _get_ping_targets()
    for env_name, targets in ping_targets.items():
        collector = PingCollector(env_name, targets)
        collectors.append(collector)
        tasks.append(
            asyncio.create_task(
                _supervised_task(f"Ping/{env_name}", collector.run)
            )
        )

    if not ping_targets:
        print("[BRIDGE] Ping — skipped (no targets configured)")

    # ---- VPN checker ----
    vpn_collector = VPNCheckCollector()
    collectors.append(vpn_collector)
    tasks.append(
        asyncio.create_task(
            _supervised_task("VPN", vpn_collector.run)
        )
    )

    active = len(tasks)
    print(f"[BRIDGE] {active} collector(s) active")
    print("[BRIDGE] ========================================")

    if not tasks:
        print("[BRIDGE] No collectors to run — exiting")
        return

    # Wait for all tasks (they run forever unless cancelled)
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        print("[BRIDGE] Shutting down collectors...")
        for c in collectors:
            c.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        print("[BRIDGE] All collectors stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[BRIDGE] Interrupted — goodbye")
