"""Configuration for Ostium CLI."""

import os
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class Network(str, Enum):
    """Network environment for Ostium."""

    mainnet = "mainnet"
    testnet = "testnet"


def get_private_key() -> str:
    """Get private key from environment."""
    key = os.getenv("PRIVATE_KEY")
    if not key:
        raise ValueError("PRIVATE_KEY not found in environment. Create a .env file.")
    return key


def get_rpc_url(network: Network) -> str:
    """Get RPC URL for the specified network."""
    if network == Network.mainnet:
        url = os.getenv("RPC_URL_MAINNET", "https://arb1.arbitrum.io/rpc")
    else:
        url = os.getenv("RPC_URL_TESTNET", "https://sepolia-rollup.arbitrum.io/rpc")
    return url
