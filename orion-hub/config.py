"""AEGIS configuration — validates environment at startup."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

REQUIRED = [
    "OPENAI_API_KEY",
    "AEGIS_SECRET_KEY",
]

OPTIONAL = [
    "ENV_CEDERVALL_WAZUH_URL",
    "ENV_CEDERVALL_WAZUH_USER",
    "ENV_CEDERVALL_WAZUH_PASSWORD",
    "ENV_CEDERVALL_WINRM_HOST",
    "ENV_CEDERVALL_WINRM_USER",
    "ENV_CEDERVALL_WINRM_PASSWORD",
    "ENV_CEDERVALL_WINRM_DOMAIN",
    "ENV_CEDERVALL_UNIFI_URL",
    "ENV_CEDERVALL_UNIFI_KEY",
    "ENV_VALVX_WAZUH_URL",
    "ENV_VALVX_WAZUH_USER",
    "ENV_VALVX_WAZUH_PASSWORD",
    "ENV_VALVX_WINRM_HOST",
    "ENV_VALVX_WINRM_USER",
    "ENV_VALVX_WINRM_PASSWORD",
    "ENV_VALVX_WINRM_DOMAIN",
    "ENV_GWSK_WINRM_HOST",
    "ENV_GWSK_WINRM_USER",
    "ENV_GWSK_WINRM_PASSWORD",
    "ENV_GWSK_OPNSENSE_URL",
    "ENV_PERSONAL_CRYPTOEDGE_HOST",
    "ENV_PERSONAL_MBG6_HOST",
    "ENV_PERSONAL_NEUROGENISYS_HOST",
    "CAMERA_MAP",
]

AEGIS_TIMEZONE = os.getenv("AEGIS_TIMEZONE", "Europe/Stockholm")
AEGIS_ORION_PORT = int(os.getenv("AEGIS_ORION_PORT", "8001"))
AEGIS_HERALD_PORT = int(os.getenv("AEGIS_HERALD_PORT", "8002"))
AEGIS_UI_PORT = int(os.getenv("AEGIS_UI_PORT", "8080"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AEGIS_SECRET_KEY = os.getenv("AEGIS_SECRET_KEY", "")


def validate():
    """Validate required env vars. Exit if missing."""
    missing = [v for v in REQUIRED if not os.getenv(v)]
    if missing:
        print(f"FATAL: Missing required environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in the values.")
        sys.exit(1)

    missing_optional = [v for v in OPTIONAL if not os.getenv(v)]
    if missing_optional:
        print(f"WARN: Optional variables not set: {', '.join(missing_optional)}")


def get_env_config(env_name: str) -> dict:
    """Get configuration for a specific environment."""
    prefix = f"ENV_{env_name}_"
    config = {}
    for key, value in os.environ.items():
        if key.startswith(prefix) and value:
            short_key = key[len(prefix):].lower()
            config[short_key] = value
    return config


def get_camera_map() -> dict:
    """Parse CAMERA_MAP env var into {mac: name} dict."""
    raw = os.getenv("CAMERA_MAP", "")
    if not raw:
        return {}
    result = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" in pair:
            mac, name = pair.split(":", 1)
            result[mac.strip().upper()] = name.strip()
    return result
