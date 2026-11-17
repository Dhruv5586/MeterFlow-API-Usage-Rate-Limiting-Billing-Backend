"""
Razorpay Payment Gateway Service
--------------------------------
Handles communication with Razorpay Test Mode API, conversion of decimal
monetary values to integer minor units, and HMAC-SHA256 signature verification
for checkout payments and incoming webhooks according to official specifications.
"""

import hmac
import hashlib
import logging
import secrets
from decimal import Decimal
from typing import Dict, Any, Optional
import httpx

from app.core.config import settings

logger = logging.getLogger("meterflow.razorpay")


class RazorpayService:
    """
    Gateway communication client for Razorpay Test Mode.
    Adheres strictly to Razorpay's official API contract and signature protocols.
    """

    RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"

    def __init__(
        self,
        key_id: Optional[str] = None,
        key_secret: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ):
        self.key_id = key_id or settings.RAZORPAY_KEY_ID
        self.key_secret = key_secret or settings.RAZORPAY_KEY_SECRET
        self.webhook_secret = webhook_secret or settings.RAZORPAY_WEBHOOK_SECRET

    @staticmethod
    def amount_to_minor_units(amount: Decimal, currency: str = "USD") -> int:
        """
        Converts decimal currency amount to gateway integer minor units.
        E.g. $29.00 -> 2900 cents; ₹1500.50 -> 150050 paise.
        """
        # ISO-4217 standard 2-decimal currencies (USD, INR, EUR, GBP, etc.)
        minor = (amount * Decimal("100")).to_integral_value()
        return int(minor)

    @staticmethod
    def minor_units_to_amount(minor_units: int, currency: str = "USD") -> Decimal:
        """Converts integer minor units back to standard Decimal currency."""
        return Decimal(minor_units) / Decimal("100")

    def create_order(
        self,
        amount_minor: int,
        currency: str,
        receipt: str,
        notes: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Creates a payment order on Razorpay Test Mode.
        If running in test/mock mode or using placeholder keys, safely returns
        a valid test order payload without contacting external endpoints.
        """
        if amount_minor <= 0:
            raise ValueError(f"Invalid order amount: {amount_minor}. Must be greater than 0.")

        is_placeholder = (
            "placeholder" in self.key_id.lower()
            or self.key_id.startswith("rzp_test_placeholder")
            or settings.ENVIRONMENT == "test"
        )

        if is_placeholder:
            mock_order_id = f"order_{secrets.token_hex(8)}"
            logger.info(f"Simulating Razorpay test order: {mock_order_id} ({amount_minor} {currency})")
            return {
                "id": mock_order_id,
                "entity": "order",
                "amount": amount_minor,
                "amount_paid": 0,
                "amount_due": amount_minor,
                "currency": currency.upper(),
                "receipt": receipt,
                "status": "created",
                "attempts": 0,
                "notes": notes or {},
            }

        payload = {
            "amount": amount_minor,
            "currency": currency.upper(),
            "receipt": receipt,
            "notes": notes or {},
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"{self.RAZORPAY_BASE_URL}/orders",
                    auth=(self.key_id, self.key_secret),
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.error(f"Failed to create Razorpay order: {exc}")
            raise RuntimeError(f"Razorpay order creation failed: {exc}") from exc

    def verify_payment_signature(
        self,
        order_id: str,
        payment_id: str,
        signature: str,
    ) -> bool:
        """
        Validates the HMAC-SHA256 signature returned by Razorpay Checkout.
        Formula: HMAC_SHA256(order_id + '|' + payment_id, key_secret) == signature
        """
        if not order_id or not payment_id or not signature:
            return False

        message = f"{order_id}|{payment_id}".encode("utf-8")
        expected_sig = hmac.new(
            self.key_secret.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_sig, signature)

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        signature_header: str,
    ) -> bool:
        """
        Validates the HMAC-SHA256 signature on incoming webhooks from Razorpay.
        Formula: HMAC_SHA256(raw_body, webhook_secret) == signature_header
        """
        if not raw_body or not signature_header:
            return False

        expected_sig = hmac.new(
            self.webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_sig, signature_header)

    def generate_test_payment_signature(self, order_id: str, payment_id: str) -> str:
        """Generates a cryptographically valid test signature using the configured secret."""
        msg = f"{order_id}|{payment_id}".encode("utf-8")
        return hmac.new(
            self.key_secret.encode("utf-8"),
            msg,
            hashlib.sha256,
        ).hexdigest()

    def generate_test_webhook_signature(self, raw_body: bytes) -> str:
        """Generates a cryptographically valid test webhook signature using configured secret."""
        return hmac.new(
            self.webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
