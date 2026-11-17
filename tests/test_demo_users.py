"""
Tests for MeterFlow Step 3: Demo Users and API Key Generation
"""

import hashlib
import re
import secrets
from scripts.create_demo_users import (
    DEMO_USERS,
    generate_secure_api_key,
)


def test_demo_users_structure():
    """Verify demo users configuration satisfies schema constraints."""
    assert len(DEMO_USERS) == 3

    emails = set()
    user_ids = set()
    for user in DEMO_USERS:
        # Check required fields
        assert "id" in user
        assert "email" in user
        assert "display_name" in user
        assert "status" in user
        assert "plan_id" in user
        assert "key_id" in user
        assert "sub_id" in user

        # Constraints
        assert user["status"] in ("active", "suspended", "closed")
        assert user["email"] == user["email"].lower()
        assert "@" in user["email"]
        assert len(user["display_name"].strip()) > 0

        # UUID format check
        uuid_regex = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        assert re.match(uuid_regex, user["id"]), f"Invalid user UUID: {user['id']}"
        assert re.match(uuid_regex, user["key_id"]), f"Invalid key UUID: {user['key_id']}"
        assert re.match(uuid_regex, user["sub_id"]), f"Invalid sub UUID: {user['sub_id']}"

        emails.add(user["email"])
        user_ids.add(user["id"])

    # Ensure uniqueness
    assert len(emails) == 3
    assert len(user_ids) == 3


def test_api_key_generation_and_hashing():
    """Verify cryptographic generation conforms to database constraints."""
    for _ in range(10):
        plaintext_key, prefix, key_hash = generate_secure_api_key()

        # Format checks
        assert plaintext_key.startswith("mf_live_")
        assert len(prefix) == 16
        assert prefix == plaintext_key[:16]

        # Hash check: 64 characters lowercase hexadecimal
        assert len(key_hash) == 64
        assert re.match(r"^[0-9a-f]{64}$", key_hash), "Hash must match database constraint ^[0-9a-f]{64}$"

        # Verify hash calculation is repeatable and accurate
        expected_hash = hashlib.sha256(plaintext_key.encode("utf-8")).hexdigest().lower()
        assert key_hash == expected_hash

        # Ensure plaintext secret is never part of the hash
        assert "mf_live_" not in key_hash
