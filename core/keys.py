"""
Key generation utilities for RSA key pairs.
"""

import streamlit as st
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import BaseModel


class KeyPair(BaseModel):
    """Pydantic model for RSA key pair."""

    private_key: str
    public_key: str
    passphrase: str
    private_key_pem_text: str


@st.cache_data
def generate_keys(passphrase: str = "q") -> KeyPair:
    """
    Generate a private/public key pair using Python cryptography library.

    Args:
        passphrase: The passphrase to encrypt the private key (default: "q")

    Returns:
        KeyPair: Pydantic model containing private_key, public_key, and
        passphrase
    """
    # Generate a 2048-bit RSA key pair
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Get the public key from the private key
    public_key = private_key.public_key()

    # Handle empty passphrase - use NoEncryption instead
    if passphrase == "":
        encryption_algorithm = serialization.NoEncryption()
    else:
        encryption_algorithm = serialization.BestAvailableEncryption(
            passphrase.encode("utf-8")
        )

    # Serialize private key to PEM format with passphrase encryption
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption_algorithm,
    ).decode("utf-8")

    # Serialize public key to PEM format
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    # Create private_key_pem_text with newlines replaced by \n for YAML/JSON
    private_key_pem_text = private_pem.replace("\n", "\\n")

    return KeyPair(
        private_key=private_pem,
        public_key=public_pem,
        passphrase=passphrase,
        private_key_pem_text=private_key_pem_text,
    )
