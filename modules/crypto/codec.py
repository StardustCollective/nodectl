import base64
import json
from modules.crypto.canonicalize import canonicalize

class JsonBinaryCodec:
    """
    Python implementation of Scala's JsonBinaryCodec that uses WebPKI.org JCS
    """
    @staticmethod
    def serialize(content):
        """Matches Scala's JsonBinaryCodec.serialize using JCS"""
        if isinstance(content, str):
            try:
                # If it's a JSON string, parse it first
                content = json.loads(content)
            except json.JSONDecodeError:
                # If not JSON, return as UTF-8 bytes
                return content.encode('utf-8')
        
        # Use the WebPKI.org JCS implementation
        return canonicalize(content)

    @staticmethod
    def serialize_data_update(content):
        """Matches Scala's JsonBinaryCodec.deriveDataUpdate.serialize"""
        # First get the canonical form using JCS
        canonical_bytes = JsonBinaryCodec.serialize(content)
        
        # Convert to base64
        base64_string = base64.b64encode(canonical_bytes).decode('utf-8')
        
        # Create the prefixed string with exact format
        prefixed_string = f"\u0019Constellation Signed Data:\n{len(base64_string)}\n{base64_string}"
        
        # Return as UTF-8 bytes
        return prefixed_string.encode('utf-8')


def compute_hash(data):
    """
    Matches Scala's JsonBinaryHasher.computeDigest implementation
    """
    from cryptography.hazmat.primitives import hashes
    
    # Get binary form
    if isinstance(data, bytes):
        binary_data = data
    else:
        binary_data = JsonBinaryCodec.serialize(data)
    
    # Compute SHA-256 hash
    digest = hashes.Hash(hashes.SHA256())
    digest.update(binary_data)
    return digest.finalize()