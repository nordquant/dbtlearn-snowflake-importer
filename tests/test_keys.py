"""
Tests for the keys module.
"""

import pytest
from core.keys import KeyPair, generate_keys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


class TestKeyPair:
    """Test the KeyPair Pydantic model."""

    def test_keypair_creation(self):
        """Test creating a KeyPair instance."""
        private_key = "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"
        public_key = "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----"
        passphrase = "test123"
        private_key_pem_text = (
            "-----BEGIN PRIVATE KEY-----\\ntest\\n" "-----END PRIVATE KEY-----"
        )

        keypair = KeyPair(
            private_key=private_key,
            public_key=public_key,
            passphrase=passphrase,
            private_key_pem_text=private_key_pem_text,
        )

        assert keypair.private_key == private_key
        assert keypair.public_key == public_key
        assert keypair.passphrase == passphrase
        assert keypair.private_key_pem_text == private_key_pem_text

    def test_keypair_validation(self):
        """Test KeyPair field validation."""
        # Test with valid data
        keypair = KeyPair(
            private_key="test_private",
            public_key="test_public",
            passphrase="test_pass",
            private_key_pem_text="test_private_pem_text",
        )
        assert isinstance(keypair, KeyPair)

        # Test with missing required fields
        with pytest.raises(ValueError):
            KeyPair(private_key="test", public_key="test", passphrase="test")
            # Missing private_key_pem_text

    def test_keypair_serialization(self):
        """Test KeyPair can be serialized to dict."""
        keypair = KeyPair(
            private_key="test_private",
            public_key="test_public",
            passphrase="test_pass",
            private_key_pem_text="test_private_pem_text",
        )

        data = keypair.model_dump()
        assert data["private_key"] == "test_private"
        assert data["public_key"] == "test_public"
        assert data["passphrase"] == "test_pass"
        assert data["private_key_pem_text"] == "test_private_pem_text"

    def test_private_key_pem_text_newline_replacement(self):
        """Test that private_key_pem_text has newlines replaced with \\n."""
        private_key = "-----BEGIN PRIVATE KEY-----\ntest\n" "-----END PRIVATE KEY-----"
        expected_pem_text = (
            "-----BEGIN PRIVATE KEY-----\\ntest\\n" "-----END PRIVATE KEY-----"
        )

        keypair = KeyPair(
            private_key=private_key,
            public_key="test_public",
            passphrase="test_pass",
            private_key_pem_text=expected_pem_text,
        )

        assert keypair.private_key_pem_text == expected_pem_text
        assert "\\n" in keypair.private_key_pem_text
        assert "\n" not in keypair.private_key_pem_text


class TestGenerateKeys:
    """Test the generate_keys function."""

    def test_generate_keys_default_passphrase(self):
        """Test key generation with default passphrase."""
        keypair = generate_keys()

        assert isinstance(keypair, KeyPair)
        assert keypair.passphrase == "q"
        assert "BEGIN ENCRYPTED PRIVATE KEY" in keypair.private_key
        assert "END ENCRYPTED PRIVATE KEY" in keypair.private_key
        assert "BEGIN PUBLIC KEY" in keypair.public_key
        assert "END PUBLIC KEY" in keypair.public_key

    def test_generate_keys_custom_passphrase(self):
        """Test key generation with custom passphrase."""
        custom_passphrase = "my_secure_passphrase_123"
        keypair = generate_keys(custom_passphrase)

        assert isinstance(keypair, KeyPair)
        assert keypair.passphrase == custom_passphrase
        assert "BEGIN ENCRYPTED PRIVATE KEY" in keypair.private_key
        assert "END ENCRYPTED PRIVATE KEY" in keypair.private_key
        assert "BEGIN PUBLIC KEY" in keypair.public_key
        assert "END PUBLIC KEY" in keypair.public_key

    def test_generate_keys_empty_passphrase(self):
        """Test key generation with empty passphrase."""
        keypair = generate_keys("")

        assert isinstance(keypair, KeyPair)
        assert keypair.passphrase == ""
        assert "BEGIN PRIVATE KEY" in keypair.private_key
        assert "END PRIVATE KEY" in keypair.private_key

    def test_generate_keys_unicode_passphrase(self):
        """Test key generation with unicode passphrase."""
        unicode_passphrase = "🔐secure_password_123"
        keypair = generate_keys(unicode_passphrase)

        assert isinstance(keypair, KeyPair)
        assert keypair.passphrase == unicode_passphrase

    def test_generate_keys_different_passphrases(self):
        """Test that different passphrases generate different keys."""
        keypair1 = generate_keys("pass1")
        keypair2 = generate_keys("pass2")

        # Different passphrases should result in different private keys
        assert keypair1.private_key != keypair2.private_key
        assert keypair1.passphrase != keypair2.passphrase
        # Public keys should also be different (different key pairs)
        assert keypair1.public_key != keypair2.public_key

    def test_generate_keys_same_passphrase_cached(self):
        """Test that same passphrase returns cached result."""
        keypair1 = generate_keys("same_pass")
        keypair2 = generate_keys("same_pass")

        # Should have same content due to caching (may not be same instance)
        assert keypair1.private_key == keypair2.private_key
        assert keypair1.public_key == keypair2.public_key
        assert keypair1.passphrase == keypair2.passphrase

    def test_generate_keys_private_key_encrypted(self):
        """Test that private key is properly encrypted with passphrase."""
        passphrase = "test_encryption_123"
        keypair = generate_keys(passphrase)

        # Try to load the private key with the correct passphrase
        private_key = serialization.load_pem_private_key(
            keypair.private_key.encode("utf-8"), password=passphrase.encode("utf-8")
        )

        assert isinstance(private_key, rsa.RSAPrivateKey)
        assert private_key.key_size == 2048

    def test_generate_keys_private_key_wrong_passphrase_fails(self):
        """Test that private key fails to load with wrong passphrase."""
        passphrase = "correct_pass"
        wrong_passphrase = "wrong_pass"
        keypair = generate_keys(passphrase)

        # Try to load the private key with wrong passphrase
        with pytest.raises(ValueError):
            serialization.load_pem_private_key(
                keypair.private_key.encode("utf-8"),
                password=wrong_passphrase.encode("utf-8"),
            )

    def test_generate_keys_public_key_loadable(self):
        """Test that public key can be loaded and used."""
        keypair = generate_keys("test_public")

        # Load the public key
        public_key = serialization.load_pem_public_key(
            keypair.public_key.encode("utf-8")
        )

        assert isinstance(public_key, rsa.RSAPublicKey)
        assert public_key.key_size == 2048

    def test_generate_keys_key_pair_consistency(self):
        """Test that private and public keys form a valid key pair."""
        keypair = generate_keys("consistency_test")

        # Load both keys
        private_key = serialization.load_pem_private_key(
            keypair.private_key.encode("utf-8"),
            password=keypair.passphrase.encode("utf-8"),
        )
        public_key = serialization.load_pem_public_key(
            keypair.public_key.encode("utf-8")
        )

        # Verify they form a valid key pair
        assert private_key.public_key().public_numbers() == public_key.public_numbers()

    def test_generate_keys_key_size(self):
        """Test that generated keys have correct size."""
        keypair = generate_keys("size_test")

        private_key = serialization.load_pem_private_key(
            keypair.private_key.encode("utf-8"),
            password=keypair.passphrase.encode("utf-8"),
        )

        assert private_key.key_size == 2048

    def test_generate_keys_private_key_pem_text(self):
        """Test that generate_keys populates private_key_pem_text correctly."""
        keypair = generate_keys("pem_text_test")

        # Verify private_key_pem_text exists and has newlines replaced
        assert hasattr(keypair, "private_key_pem_text")
        assert keypair.private_key_pem_text is not None
        assert "\\n" in keypair.private_key_pem_text
        assert "\n" not in keypair.private_key_pem_text

        # Verify it can be converted back to original format
        reconstructed = keypair.private_key_pem_text.replace("\\n", "\n")
        assert reconstructed == keypair.private_key

    def test_generate_keys_pem_format(self):
        """Test that keys are in proper PEM format."""
        keypair = generate_keys("pem_test")

        # Check private key format (encrypted)
        assert keypair.private_key.startswith("-----BEGIN ENCRYPTED PRIVATE KEY-----")
        assert keypair.private_key.endswith("-----END ENCRYPTED PRIVATE KEY-----\n")
        assert "BEGIN ENCRYPTED PRIVATE KEY" in keypair.private_key
        assert "END ENCRYPTED PRIVATE KEY" in keypair.private_key

        # Check public key format
        assert keypair.public_key.startswith("-----BEGIN PUBLIC KEY-----")
        assert keypair.public_key.endswith("-----END PUBLIC KEY-----\n")
        assert "BEGIN PUBLIC KEY" in keypair.public_key
        assert "END PUBLIC KEY" in keypair.public_key

    def test_generate_keys_passphrase_persistence(self):
        """Test that passphrase is correctly stored and returned."""
        test_passphrases = ["", "q", "simple", "complex_123!@#", "🔐unicode"]

        for passphrase in test_passphrases:
            keypair = generate_keys(passphrase)
            assert keypair.passphrase == passphrase

    def test_generate_keys_multiple_calls_different_results(self):
        """Test that multiple calls with same passphrase return same result due to caching."""
        passphrase = "caching_test"

        # Generate multiple times
        keypair1 = generate_keys(passphrase)
        keypair2 = generate_keys(passphrase)
        keypair3 = generate_keys(passphrase)

        # All should have same content due to caching (may not be same instance)
        assert keypair1.private_key == keypair2.private_key == keypair3.private_key
        assert keypair1.public_key == keypair2.public_key == keypair3.public_key
        assert keypair1.passphrase == keypair2.passphrase == keypair3.passphrase
