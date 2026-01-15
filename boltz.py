#!/usr/bin/env python3
"""
Boltz API Client for Submarine Swaps
Supports both normal submarine swaps (Chain -> Lightning) and reverse swaps (Lightning -> Chain)
"""
import bolt11
import requests,datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class SwapPair:
    """Represents a swap pair configuration"""
    rate: float
    min_amount: int
    max_amount: int
    percentage_fee: float
    miner_fees: Dict[str, Any]


class BoltzClient:
    """Client for interacting with the Boltz API"""

    # Available endpoints
    MAINNET_URL = "https://api.boltz.exchange/v2"
    TESTNET_URL = "https://api.testnet.boltz.exchange/v2"

    def __init__(self, network: str = "mainnet"):
        """
        Initialize Boltz client

        Args:
            network: Either 'mainnet' or 'testnet'
        """
        if network not in ["mainnet", "testnet"]:
            raise ValueError("Network must be either 'mainnet' or 'testnet'")

        self.network = network
        self.base_url = self.MAINNET_URL if network == "mainnet" else self.TESTNET_URL
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "BoltzPythonClient/1.0"
        })

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """
        Make HTTP request to Boltz API

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint path
            data: Request payload for POST requests

        Returns:
            Response JSON as dictionary
        """
        url = f"{self.base_url}/{endpoint}"

        try:
            if method.upper() == "GET":
                response = self.session.get(url)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            if hasattr(e.response, 'text'):
                print(f"Response: {e.response.text}")
            raise

    def get_pairs(self) -> Dict[str, SwapPair]:
        """
        Get current swap pairs and their pricing information

        Returns:
            Dictionary of swap pairs with pricing details
        """
        response = self._make_request("GET", "swap/submarine")

        pairs = {}
        for pair_name, pair_dict in response.items():
            for pair_name_two, pair_data in pair_dict.items():
                pairs[pair_name] = SwapPair(
                    rate=pair_data.get("rate", 0),
                    min_amount=pair_data.get("limits", {}).get("minimal", 0),
                    max_amount=pair_data.get("limits", {}).get("maximal", 0),
                    percentage_fee=pair_data.get("fees", {}).get("percentage", 0),
                    miner_fees=pair_data.get("fees", {}).get("minerFees", {})
                )

        return pairs

    def get_reverse_pairs(self) -> Dict[str, SwapPair]:
        """
        Get current reverse swap pairs and their pricing information

        Returns:
            Dictionary of reverse swap pairs with pricing details
        """
        response = self._make_request("GET", "swap/reverse")

        pairs = {}
        for pair_name, pair_data in response.get("pairs", {}).items():
            pairs[pair_name] = SwapPair(
                rate=pair_data.get("rate", 0),
                min_amount=pair_data.get("limits", {}).get("minimal", 0),
                max_amount=pair_data.get("limits", {}).get("maximal", 0),
                percentage_fee=pair_data.get("fees", {}).get("percentage", 0),
                miner_fees=pair_data.get("fees", {}).get("minerFees", {})
            )

        return pairs

    def create_submarine_swap(
            self,
            invoice: str,
            from_currency: str = "BTC",
            to_currency: str = "BTC",
            refund_public_key: Optional[str] = None
    ) -> Dict:
        """
        Create a normal submarine swap (Chain -> Lightning)

        Args:
            invoice: Lightning invoice to be paid
            from_currency: Source currency (e.g., 'BTC', 'L-BTC')
            to_currency: Destination currency (e.g., 'BTC', 'L-BTC')
            refund_public_key: Public key for refunds (hex encoded). If None, generates one.

        Returns:
            Swap creation response with lockup address and details
        """

        payload = {
            "invoice": invoice,
            "from": from_currency,
            "to": to_currency,
            "refundPublicKey": refund_public_key
        }

        return self._make_request("POST", "swap/submarine", payload)

    def create_reverse_swap(
            self,
            amount: int,
            from_currency: str = "BTC",
            to_currency: str = "BTC",
            claim_public_key: str = None,
            preimage_hash: str = None,
    ) -> Dict:
        """
        Create a reverse submarine swap (Lightning -> Chain)

        Args:
            amount: Amount in satoshis
            from_currency: Source currency (e.g., 'BTC', 'L-BTC')
            to_currency: Destination currency (e.g., 'BTC', 'L-BTC')
            claim_public_key: Public key for claiming (hex encoded). If None, generates one.
            preimage_hash: SHA256 hash of preimage (hex encoded). If None, generates one.

        Returns:
            Reverse swap creation response with invoice and lockup details
        """
        # Generate claim key if not provided

        payload = {
            "invoiceAmount": amount,
            "from": from_currency,
            "to": to_currency,
            "claimPublicKey": claim_public_key,
            "preimageHash": preimage_hash
        }

        return self._make_request("POST", "swap/reverse", payload)

    def get_swap_status(self, swap_id: str) -> Dict:
        """
        Get the status of a swap

        Args:
            swap_id: ID of the swap to query

        Returns:
            Swap status information
        """
        return self._make_request("GET", f"swap/{swap_id}")


def print_pairs(pairs: Dict[str, SwapPair], title: str):
    """Pretty print swap pairs"""
    print(f"\n{title}")
    print("=" * 80)

    for pair_name, pair in pairs.items():
        print(f"\nPair: {pair_name}")
        print(f"  Rate: {pair.rate}")
        print(f"  Min Amount: {pair.min_amount:,} sats")
        print(f"  Max Amount: {pair.max_amount:,} sats")
        print(f"  Fee: {pair.percentage_fee}%")
        print(f"  Miner Fees: {pair.miner_fees}")

def main():
    # Example Lightning invoices (testnet examples)
    examples = [
        # Testnet invoice example
        "lnbc777777777777777777777777",

    ]

    print("Lightning Invoice Payment Hash Extractor")
    print("=" * 80)

    for i, invoice in enumerate(examples, 1):
        print(f"\nExample {i}:")
        print(f"Invoice: {invoice[:50]}...")
        invoice_data=bolt11.decode(invoice)
        # Extract just the payment hash
        payment_hash = invoice_data.payment_hash
        if payment_hash:
            print(f"Payment Hash: {payment_hash}")
        else:
            print("Failed to extract payment hash")
            quit()
    """Example usage of the Boltz client"""

    # Initialize clients for both networks
    print("Boltz API Submarine Swap Client")
    print("=" * 80)

    # Create mainnet client
    print("\n--- TESTNET ---")
    testnet_client = BoltzClient(network="mainnet")

    # Get and display submarine swap pricing
    try:
        submarine_pairs = testnet_client.get_pairs()
        print_pairs(submarine_pairs, "Submarine Swap Pairs (Chain -> Lightning)")
    except Exception as e:
        print(f"Error fetching submarine pairs: {e}")

    # Get and display reverse swap pricing
    try:
        reverse_pairs = testnet_client.get_reverse_pairs()
        print_pairs(reverse_pairs, "Reverse Swap Pairs (Lightning -> Chain)")
    except Exception as e:
        print(f"Error fetching reverse pairs: {e}")


    # Example: Create a submarine swap (commented out - requires real invoice)
    """
    print("\n\n--- CREATING SUBMARINE SWAP ---")
    invoice = "lnbc..."  # Your Lightning invoice here
    try:
        swap_result = mainnet_client.create_submarine_swap(
            invoice=invoice,
            from_currency="BTC",
            to_currency="BTC"
        )
        print(f"Swap created successfully!")
        print(f"Swap ID: {swap_result.get('id')}")
        print(f"Lockup Address: {swap_result.get('address')}")
        print(f"Expected Amount: {swap_result.get('expectedAmount')} sats")
    except Exception as e:
        print(f"Error creating swap: {e}")

    # Example: Create a reverse swap (commented out)
    """
    print("\n\n--- CREATING REVERSE SWAP ---")
    btc_address='myaddress'
    bytes_object = btc_address.encode('utf-8')  # Encode the string to bytes
    btc_address_hex_string = bytes_object.hex()

    preimage_bytes=payment_hash.encode('utf-8')
    preimage_hex=preimage_bytes.hex()
    try:
        reverse_result = testnet_client.create_reverse_swap(
            amount=100000,  # 100,000 sats
            from_currency="BTC",
            to_currency="BTC",
            #claim_public_key=btc_address_hex_string,
            claim_public_key=btc_address,
            preimage_hash=payment_hash
        )
        print(f"Reverse swap created successfully!")
        print(f"Swap ID: {reverse_result.get('id')}")
        print(f"Invoice: {reverse_result.get('invoice')}")
        print(f"Lockup Address: {reverse_result.get('lockupAddress')}")
    except Exception as e:
        print(f"Error creating reverse swap: {e}")


if __name__ == "__main__":
    main()