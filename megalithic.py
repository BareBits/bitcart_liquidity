import json
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import requests
MAINNET_PUBKEY="038a9e56512ec98da2b5789761f7af8f280baf98a09282360cd6ff1381b5e889bf@64.23.162.51:9735"
MUTINY_PUBKEY="03e30fda71887a916ef5548a4d02b06fe04aaa1a8de9e24134ce7f139cf79d7579@64.23.192.68:9736"
def pubkey_from_uri(uri:str):
    return uri.split('@')[0]
@dataclass
class NetworkConfig:
    """Configuration for different networks."""
    rest_base_url: str
    ln_peer_uri: str

class Network(Enum):
    """Available networks for Megalithic LSPS1 service."""
    MAINNET = "mainnet"
    TESTNET = "testnet3"
    MUTINYNET = "mutinynet"

NETWORK_CONFIGS = {
    Network.MAINNET: NetworkConfig(
        rest_base_url="https://megalithic.me/api/lsps1/v1",
        ln_peer_uri=MAINNET_PUBKEY
    ),
    Network.MUTINYNET: NetworkConfig(
        rest_base_url="https://lsp1.mutiny.megalith-node.com/api/lsps1/v1",
        ln_peer_uri=MUTINY_PUBKEY
    )
}



class OrderState(Enum):
    """Possible states for a channel order."""
    CREATED = "CREATED"
    EXPECT_PAYMENT = "EXPECT_PAYMENT"
    PAID = "PAID"
    OPENING = "OPENING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class MegalithicLSPClient:
    """
    Client for interacting with Megalithic LSPS1 API.

    The LSPS1 specification provides a way to purchase Lightning Network channels
    in advance, with confirmation required before the channel opens.
    """

    def __init__(self, network: Network = Network.MAINNET, timeout: int = 30):
        """
        Initialize the Megalithic LSPS1 client.

        Args:
            network: The network to use (mainnet, testnet, or mutinynet)
            timeout: Request timeout in seconds
        """
        self.network = network
        self.config = NETWORK_CONFIGS[network]
        self.base_url = self.config.rest_base_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            **kwargs: Additional arguments to pass to requests

        Returns:
            JSON response as dictionary

        Raises:
            requests.exceptions.RequestException: For network errors
            ValueError: For invalid responses
        """
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.request(
                method=method,
                url=url,
                timeout=self.timeout,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise requests.exceptions.RequestException(
                f"Request failed for {url}: {str(e)}"
            )
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from {url}: {str(e)}")

    def get_info(self) -> Dict[str, Any]:
        """
        Get information about the LSP's channel service options and constraints.

        Returns:
            Dictionary containing:
            - max_channel_balance_sat: Maximum channel balance in satoshis
            - max_channel_expiry_blocks: Maximum channel expiry in blocks
            - max_initial_client_balance_sat: Maximum initial client balance
            - max_initial_lsp_balance_sat: Maximum initial LSP balance
            - min_channel_balance_sat: Minimum channel balance in satoshis
            - min_funding_confirms_within_blocks: Minimum funding confirmation blocks
            - min_initial_client_balance_sat: Minimum initial client balance
            - min_initial_lsp_balance_sat: Minimum initial LSP balance
            - min_onchain_payment_confirmations: Minimum onchain payment confirmations
            - min_onchain_payment_size_sat: Minimum onchain payment size
            - min_required_channel_confirmations: Minimum required channel confirmations
            - supports_zero_channel_reserve: Whether zero channel reserve is supported
            - uris: List of node URIs for connection
        """
        return self._make_request('GET', '/get_info')

    def create_order(
            self,
            public_key: str,
            lsp_balance_sat: int,
            client_balance_sat: int = 0,
            required_channel_confirmations: int = 3,
            funding_confirms_within_blocks: int = 6,
            channel_expiry_blocks: int = 26280,
            token: str = "",
            refund_onchain_address: str = "",
            announce_channel: bool = False
    ) -> Dict[str, Any]:
        """
        Create a new channel order.

        Args:
            public_key: Public key of the node to open channel with
            lsp_balance_sat: LSP balance in satoshis
            client_balance_sat: Client balance in satoshis (default: 0)
            required_channel_confirmations: Required channel confirmations (default: 6)
            funding_confirms_within_blocks: Funding confirms within blocks (default: 6)
            channel_expiry_blocks: Channel expiry in blocks (default: 13000)
            token: Optional authentication token
            refund_onchain_address: Optional onchain refund address
            announce_channel: Whether to announce the channel publicly (default: False)

        Returns:
            Dictionary containing:
            - order_id: Unique order identifier
            - order_state: Current state of the order
            - lsp_balance_sat: LSP balance in satoshis
            - client_balance_sat: Client balance in satoshis
            - created_at: Order creation timestamp
            - channel: Channel information (if opened)
            - payment: Payment information including bolt11 invoice
            - announce_channel: Whether channel will be announced
            - channel_expiry_blocks: Channel expiry in blocks
            - funding_confirms_within_blocks: Funding confirmation blocks
            - token: Authentication token (if provided)
        """
        payload = {
            "public_key": public_key.split('@')[0],
            "lsp_balance_sat": str(lsp_balance_sat),
            "client_balance_sat": str(client_balance_sat),
            "required_channel_confirmations": required_channel_confirmations,
            "funding_confirms_within_blocks": funding_confirms_within_blocks,
            "channel_expiry_blocks": channel_expiry_blocks,
            "announce_channel": announce_channel
        }
        #payload=json.dumps(payload)
        return self._make_request('POST', '/create_order', json=payload)

    def get_order(self, order_id: str) -> Dict[str, Any]:
        """
        Get the status and details of an existing order.

        Args:
            order_id: The unique identifier of the order

        Returns:
            Dictionary containing:
            - order_id: Unique order identifier
            - order_state: Current state of the order
            - lsp_balance_sat: LSP balance in satoshis
            - client_balance_sat: Client balance in satoshis
            - created_at: Order creation timestamp
            - channel: Channel information (if opened)
            - payment: Payment information including bolt11 invoice
            - announce_channel: Whether channel is announced
            - channel_expiry_blocks: Channel expiry in blocks
            - funding_confirms_within_blocks: Funding confirmation blocks
            - token: Authentication token (if provided)
        """
        params = {"order_id": order_id}
        return self._make_request('GET', '/get_order', params=params)

    def get_lightning_peer_uri(self) -> str:
        """
        Get the Lightning Network peer URI for custom message communication.

        Returns:
            The Lightning Network peer URI string for the configured network
        """
        return self.config.ln_peer_uri

    def get_network_info(self) -> Dict[str, str]:
        """
        Get complete network configuration information.

        Returns:
            Dictionary containing:
            - network: Current network name
            - rest_base_url: REST API base URL
            - ln_peer_uri: Lightning Network peer URI
        """
        return {
            "network": self.network.value,
            "rest_base_url": self.config.rest_base_url,
            "ln_peer_uri": self.config.ln_peer_uri
        }


class MegalithicLSPS1Helper:
    """Helper class with utility functions for working with Megalithic LSPS1 API."""

    @staticmethod
    def parse_payment_info(payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse payment information from an order response.

        Args:
            payment_data: Payment data from order response

        Returns:
            Parsed payment information
        """
        if not payment_data:
            return {}

        bolt11_data = payment_data.get('bolt11', {})

        return {
            'invoice': bolt11_data.get('invoice'),
            'order_total_sat': bolt11_data.get('order_total_sat'),
            'fee_total_sat': bolt11_data.get('fee_total_sat'),
            'state': bolt11_data.get('state'),
            'expires_at': bolt11_data.get('expires_at')
        }

    @staticmethod
    def is_order_complete(order: Dict[str, Any]) -> bool:
        """
        Check if an order is complete.

        Args:
            order: Order data from API response

        Returns:
            True if order is complete, False otherwise
        """
        return order.get('order_state') == OrderState.COMPLETED.value

    @staticmethod
    def is_order_failed(order: Dict[str, Any]) -> bool:
        """
        Check if an order has failed.

        Args:
            order: Order data from API response

        Returns:
            True if order has failed, False otherwise
        """
        return order.get('order_state') == OrderState.FAILED.value

    @staticmethod
    def is_payment_required(order: Dict[str, Any]) -> bool:
        """
        Check if payment is required for an order.

        Args:
            order: Order data from API response

        Returns:
            True if payment is required, False otherwise
        """
        return order.get('order_state') == OrderState.EXPECT_PAYMENT.value

    @staticmethod
    def get_channel_info(order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract channel information from an order.

        Args:
            order: Order data from API response

        Returns:
            Channel information if available, None otherwise
        """
        return order.get('channel')

    @staticmethod
    def calculate_total_capacity(lsp_balance: int, client_balance: int) -> int:
        """
        Calculate total channel capacity.

        Args:
            lsp_balance: LSP balance in satoshis
            client_balance: Client balance in satoshis

        Returns:
            Total channel capacity in satoshis
        """
        return lsp_balance + client_balance
