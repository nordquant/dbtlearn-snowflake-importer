import base64

import pytest
from core.keys import generate_keys
from core.snowflake import extract_snowflake_account, is_valid_snowflake_account
from cryptography.hazmat.primitives import serialization
from streamlit_app import get_dbt_connection


class TestExtractSnowflakeAccount:
    def test_simple_account_identifier(self):
        assert extract_snowflake_account("jdehewj-vmb00970") == "jdehewj-vmb00970"

    def test_account_with_snowflake_domain(self):
        assert (
            extract_snowflake_account("jhkfheg-qb43765.snowflakecomputing.com")
            == "jhkfheg-qb43765"
        )

    def test_full_url_with_path(self):
        assert (
            extract_snowflake_account(
                "https://jhkfheg-qb43765.snowflakecomputing.com/console/login"
            )
            == "jhkfheg-qb43765"
        )

    def test_account_with_aws_suffix(self):
        assert (
            extract_snowflake_account("jdehewj-vmb00970.aws") == "jdehewj-vmb00970.aws"
        )

    def test_simple_aws_account(self):
        assert extract_snowflake_account("xxxxxx.aws") == "xxxxxx.aws"

    def test_empty_string(self):
        assert extract_snowflake_account("") == ""

    def test_none_input(self):
        assert extract_snowflake_account(None) is None

    def test_whitespace_only(self):
        assert extract_snowflake_account("   ") == "   "

    def test_url_with_https(self):
        assert (
            extract_snowflake_account("https://myaccount-123.snowflakecomputing.com")
            == "myaccount-123"
        )

    def test_url_with_http(self):
        assert (
            extract_snowflake_account("http://myaccount-123.snowflakecomputing.com")
            == "myaccount-123"
        )

    def test_account_with_trailing_whitespace(self):
        assert extract_snowflake_account("  jdehewj-vmb00970  ") == "jdehewj-vmb00970"

    def test_complex_url_with_query_params(self):
        assert (
            extract_snowflake_account(
                "https://abc-def123.snowflakecomputing.com/console/login?returnUrl=%2Fconsole"
            )
            == "abc-def123"
        )

    def test_account_with_additional_domain_parts(self):
        assert (
            extract_snowflake_account(
                "myaccount-123.us-east-1.aws.snowflakecomputing.com"
            )
            == "myaccount-123.us-east-1.aws"
        )

    def test_single_word_account(self):
        assert extract_snowflake_account("singleword") == "singleword"

    def test_alphanumeric_account(self):
        assert extract_snowflake_account("abc123-def456") == "abc123-def456"

    def test_fallback_for_invalid_pattern(self):
        # Should return original input if no pattern matches
        assert extract_snowflake_account("invalid..pattern..") == "invalid..pattern.."


class TestIsValidSnowflakeAccount:
    def test_valid_account_with_hyphen(self):
        assert is_valid_snowflake_account("frgcsyo-ie17820") is True

    def test_valid_account_with_aws_suffix(self):
        assert is_valid_snowflake_account("frgcsyo-ie17820.aws") is True

    def test_valid_simple_account(self):
        assert is_valid_snowflake_account("abc123") is True

    def test_valid_single_word_account(self):
        assert is_valid_snowflake_account("singleword") is True

    def test_valid_account_with_aws_only(self):
        assert is_valid_snowflake_account("abc123.aws") is True

    def test_invalid_empty_string(self):
        assert is_valid_snowflake_account("") is False

    def test_invalid_none_input(self):
        assert is_valid_snowflake_account(None) is False

    def test_invalid_whitespace_only(self):
        assert is_valid_snowflake_account("   ") is False

    def test_invalid_with_special_chars(self):
        assert is_valid_snowflake_account("invalid@account") is False

    def test_invalid_with_dots_in_middle(self):
        assert is_valid_snowflake_account("invalid.account.format") is False

    def test_invalid_with_multiple_hyphens(self):
        assert is_valid_snowflake_account("too-many-hyphens") is False

    def test_invalid_with_underscores(self):
        assert is_valid_snowflake_account("invalid_account") is False

    def test_invalid_with_spaces(self):
        assert is_valid_snowflake_account("invalid account") is False

    def test_snowflake_url_as_bad_input(self):
        # Test the specific URL provided by the user as an example of bad input
        url = "snowflake://preset@odsflka-ul86934/AIRBNB?role=REPORTER&warehouse=COMPUTE_WH"
        extracted_account = extract_snowflake_account(url)
        # The extraction should return the original input since it doesn't match expected patterns
        assert extracted_account == url
        # This should be considered invalid input that triggers a warning
        assert is_valid_snowflake_account(extracted_account) is False


class TestPrivateKeyDecryption:
    """Test private key decryption and get_dbt_connection functionality."""

    def test_key_generation_and_decryption(self):
        """Test that we can generate keys and decrypt them properly."""
        # Generate a key pair
        keypair = generate_keys(passphrase="q")

        # Verify key pair properties
        assert len(keypair.private_key) > 0
        assert len(keypair.public_key) > 0
        assert keypair.passphrase == "q"

        # Convert PEM text back to actual PEM format
        private_key_pem = keypair.private_key_pem_text.replace("\\n", "\n")

        # Load the private key from PEM format
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"),
            password=b"q",  # The passphrase used to encrypt the key
            backend=None,
        )

        # Verify we can convert to DER format (unencrypted)
        private_key_der = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        # Verify we can base64 encode the DER key
        private_key_b64 = base64.b64encode(private_key_der).decode("utf-8")
        assert len(private_key_b64) > 0

    def test_get_dbt_connection_key_processing(self):
        """Test that get_dbt_connection processes the private key correctly."""
        # Generate a key pair
        keypair = generate_keys(passphrase="q")

        # Test parameters (using dummy values since we don't have real Snowflake access)
        test_account = "test-account"
        test_login = "test_user"
        test_role = "TEST_ROLE"

        # This will likely fail with connection error, but we want to test the key processing
        # Must enter the context manager to actually execute the connection code
        with pytest.raises(Exception) as exc_info:
            with get_dbt_connection(test_account, test_login, test_role, keypair.private_key):
                pass

        # Check that it's NOT a key decryption error
        error_msg = str(exc_info.value).lower()
        assert "incorrect password" not in error_msg
        assert "could not decrypt key" not in error_msg
        assert "failed to load private key" not in error_msg
        assert "asn.1 parsing error" not in error_msg

        # It should be a connection error (expected due to invalid account)
        # This confirms the key was processed correctly
        assert (
            "404" in error_msg or "not found" in error_msg or "connection" in error_msg
        )

    def test_private_key_format_conversion(self):
        """Test the complete private key format conversion process."""
        # Generate a key pair
        keypair = generate_keys(passphrase="q")

        # Test the conversion process step by step
        private_key_pem = keypair.private_key_pem_text.replace("\\n", "\n")

        # Step 1: Load encrypted PEM key
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"),
            password=b"q",
            backend=None,
        )

        # Step 2: Convert to unencrypted DER
        private_key_der = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        # Step 3: Base64 encode
        private_key_b64 = base64.b64encode(private_key_der).decode("utf-8")

        # Verify the result is valid base64
        try:
            decoded = base64.b64decode(private_key_b64)
            assert len(decoded) > 0
        except Exception:
            pytest.fail("Generated base64 key is not valid")

        # Verify the DER key can be loaded back
        try:
            loaded_der_key = serialization.load_der_private_key(
                private_key_der, password=None, backend=None
            )
            assert loaded_der_key is not None
        except Exception:
            pytest.fail("Generated DER key cannot be loaded back")
