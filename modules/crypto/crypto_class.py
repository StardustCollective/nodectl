import binascii
import json
import brotli 
import hashlib

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from cryptography.hazmat.backends import default_backend

from termcolor import cprint, colored

from modules.crypto.canonicalize import canonicalize
from modules.crypto.codec import compute_hash


class NodeCtlCryptoClass:
    def __init__(self,command_obj):
        self.log = command_obj.get("log",False)
        self.data = command_obj.get("data",None)
        self.private_path = command_obj.get("private_path", False)
        self.public_path = command_obj.get("public_path", False)
        self.config_obj = command_obj.get("config_obj",False)
        self.profile = command_obj.get("profile", False)
        self.protocol = command_obj.get("protocol", "simple")  # Default to simple protocol
        self.error_messages = command_obj.get("error_messages",False)
        self.serialize_should_sort = command_obj.get("should_sort",True)
        self.serialize_should_remove_nulls = command_obj.get("remove_nulls",True)
        self.hash_type = command_obj.get("hash_type","standard")

        self.p12p = command_obj.get("p12p",False)

        self.log_key = "main"
        self.error = False

        self.hex_private_key = False
        self.hex_public_key = False

        self.serial_brotli_data_bytes = None
        self.serial_brotli_data_hex = None
        self.sorted_data = None
        self.nulls_removed_data = None
        self.utf8_bytes_data = None
        self.hashed_data_hex_32 = None
        self.hashed_data_hex_64 = None
        self.signature = None
        self.hex_signature = None
        self.external_key = None
        self.debug = False

    def log_data(self):
        self._handle_log_msg("debug",f"Brotli version: {brotli.__version__}.")
        self._handle_log_msg("debug",f"Brotli module path: {brotli.__file__}.")
        self._handle_log_msg("debug",f"data: {self.data}")
        self._handle_log_msg("debug",f"utf8_bytes_data: {self.utf8_bytes_data}")
        self._handle_log_msg("debug",f"hashed_data_hex_32: {self.hashed_data_hex_32}")
        self._handle_log_msg("debug",f"hashed_data_hex_64: {self.hashed_data_hex_64}")
        self._handle_log_msg("debug",f"hex_signature: {self.hex_signature}")
        self._handle_log_msg("debug",f"serial_brotli_data_hex: {self.serial_brotli_data_hex}")
        self._handle_log_msg("debug",f"signature: {self.signature}")

        if self.debug:
            cprint("  Debug or Verbose mode detected:","magenta",end="\n\n")

            cprint("  Brotli version:","cyan",end=" ")
            cprint(f"{brotli.__version__,}","yellow")

            cprint("  Brotli module path:","cyan", end=" ") 
            cprint(f"{brotli.__file__}","yellow",end="\n\n")

            cprint(f"  data:","cyan",end=" ")
            cprint(f"{self.data}","yellow",end="\n\n")

            cprint("  sorted_data:","cyan", end=" ")
            cprint(f"{self.sorted_data}","yellow", end="\n\n")

            cprint("  nulls_removed_data:","cyan",end=" ")
            cprint(f"{self.nulls_removed_data}","yellow",end="\n\n")

            cprint("  utf8_bytes_data:","cyan",end=" ")
            cprint(f"{self.utf8_bytes_data}","yellow",end="\n\n")

            cprint("  serial_brotli_data_hex:","cyan", end=" ")
            cprint(f"{self.serial_brotli_data_hex}","yellow", end="\n\n")

            cprint("  signature:", "cyan", end=" ")
            cprint(f"{self.signature}", "yellow", end="\n\n")

            cprint("  hex_signature:", "cyan", end=" ")
            cprint(f"{self.hex_signature}", "yellow", end="\n\n")

            cprint(f"  hashed_data_hex_32:","cyan", end=" ")
            cprint(f"{self.hashed_data_hex_32}","yellow", end="\n\n")

            cprint(f"  hashed_data_hex_64:", "cyan", end=" ")
            cprint(f"{self.hashed_data_hex_64}", "yellow", end="\n\n")

            prompt = colored("  Any key to continue...","green",attrs=["bold"])
            _ = input(prompt)


    def _handle_log_msg(self,level,msg):
        if not self.log: return
        msg = f"nodeCtlCrypto --> {msg}"
        log_method = getattr(self.log.logger[self.log_key], level.lower(), None)
        if log_method and callable(log_method):
            log_method(msg)


    def hash_data(self):
        self._handle_log_msg("info","Computing data package hash.")
        
        if self.hash_type == "standard":
            try:
                self.hashed_data_hex_32 = hashlib.sha256(bytes.fromhex(self.data)).hexdigest()
            except:
                self.hashed_data_hex_32 = hashlib.sha256(self.serial_brotli_data_bytes).hexdigest()
        else:
            data_hash_bytes = compute_hash(self.data)
            self.hashed_data_hex_32 = data_hash_bytes.hex()
        
        self._handle_log_msg("info","Convert hex hash to UTF-8 bytes (matching Scala's Hash.value.getBytes).")
        hashed_data_hex_64 = self.hashed_data_hex_32.encode('utf-8')
        self.hashed_data_hex_64 = hashed_data_hex_64.hex()


    def _sort_object_keys(self,obj):
        if not isinstance(obj, dict):
            return obj

        if isinstance(self.data, list):
            return [self._sort_object_keys(item) for item in obj]

        return {k: self._sort_object_keys(obj[k]) for k in sorted(obj.keys())}


    def _remove_nulls(self,obj):
        def process_value(value):
            if value is None:
                return None
            if isinstance(value, list):
                return [process_value(v) for v in value if process_value(v) is not None]
            if isinstance(value, dict):
                return self._remove_nulls(value)
            return value

        return {k: process_value(v) for k, v in obj.items() if process_value(v) is not None}
    

    def _prepare_key_paths(self):
        error = False
        for n, key_path in enumerate([self.private_path, self.public_path]):
            if key_path:
                key = self.set_external_key(self.private_path)
                if not key: 
                    error = True
                    break
                
                if n < 1:
                    self.private_key = key
                else:
                    self.public_key = key
        
        if error:
            self.error_messages.error_code_messages({
                "line_code": "invalid_data",
                "error_code": "crylib-169",
                "extra": "extracting keys from external file.",
                "extra2": "Please verify your private/public keys and key paths."
            })


    def sign_data(self):
        self._handle_log_msg("info","Sign the UTF-8 encoded hash.")
        self.signature = self.private_key.sign(
            bytes.fromhex(self.hashed_data_hex_64),
            ec.ECDSA(hashes.SHA512())
        )


    def set_signature_hex(self):
        self.hex_signature = binascii.hexlify(self.signature).decode()

    
    def verify_signature(self):
        try:
            self.public_key.verify(
                bytes.fromhex(self.hex_signature),
                bytes.fromhex(self.hashed_data_hex_64),
                ec.ECDSA(hashes.SHA512())
            )
            self._handle_log_msg("info","Signature verified successfully.")
        except Exception as e:
            self.error = str(e)
            self._handle_log_msg("info",f"Signature verification failed: {e}.")
        finally:
            return self.error
        

    def serialize_brotli(self):
        compression_level = 2
        self.sorted_data = self._sort_object_keys(self.data) if self.serialize_should_sort else self.data
        self.nulls_removed_data = self._remove_nulls(self.sorted_data) if self.serialize_should_remove_nulls else self.sorted_data
        json_string = json.dumps(self.nulls_removed_data, separators=(',',':'))
        utf8_bytes_data = json_string.encode('utf-8')
        self.utf8_bytes_data = utf8_bytes_data.hex()
        self.serial_brotli_data_bytes = brotli.compress(utf8_bytes_data, quality=compression_level)
        self.serial_brotli_data_hex = self.serial_brotli_data_bytes.hex()


    def export_64char_hex_private_key(self):
        with open(self.private_path, "rb") as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None  # Provide a password if your key is encrypted
            )
        private_number = private_key.private_numbers().private_value
        self.private_key_hex = f"{private_number:064x}"
    
     
    def ensure_canonical_bytes(self):
        if isinstance(self.data,str) or isinstance(self.data,dict):
            try:
                self.data = canonicalize(self.data)
                self._handle_log_msg("info",f"Canonicalized data successful: [{self.data}].")
            except Exception as e:
                self._handle_log_msg("error",f"Canonicalize failed with: {e} | raising TypeError.")
                raise TypeError()
    

    def get_valid_ecdsa_publickey(self):
        if self.external_key is None:
            key = self.public_path

        key_str = ''
        with open(key, "r") as pem_file:
            pem_data = pem_file.read()
            lines = pem_data.splitlines()
            for line in lines:
                if "BEGIN" not in line and "END" not in line:
                    key_str += line
                    
        public_key = serialization.load_pem_public_key(pem_data.encode(), backend=default_backend())
        key_bits = public_key.key_size
        key_str = key_str.strip()

        if key_bits == 256:
            raw_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.X962,  
                format=serialization.PublicFormat.UncompressedPoint  
            )
            # Skip the 0x04 prefix (first byte) to get just X + Y (64 bytes)
            key_coords = raw_bytes[1:] 
            hex_key = key_coords.hex()
            return hex_key
        return False


    def set_external_key(self,key_path):
        self._handle_log_msg(f"info",f"loading external key [{key_path}].")
        try:
            with open(key_path, "rb") as key_file:
                key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=None
                )    
            return key
        except Exception as e:
            self._handle_log_msg("critical",f"Unable to find or load valid key [{key_path}].")
            return False


    def load_keys(self):
        self.private_key = serialization.load_pem_private_key(
            self.private_key,
            password=None
        )
        self.public_key = serialization.load_pem_public_key(
            self.public_key,
        )


    def handle_hex_keys(self):
        self._handle_log_msg("info", "Attempting to load keys from hex strings.")

        try:
            private_key_bytes = bytes.fromhex(self.hex_private_key)
            private_value = int.from_bytes(private_key_bytes, byteorder='big')
        except Exception as e:
            self._handle_log_msg("error",f"An error was received attempting to ")
            self.error = str(e)
            return

        private_key = ec.derive_private_key(
            private_value,
            ec.SECP256K1(),
            default_backend()
        )
        public_key = private_key.public_key()

        # Serialize the private key to PEM format for verification
        self.private_key = private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=NoEncryption()
        )

        self.public_key = public_key.public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo
        )
    

    def extract_p12_keys(self):
        self._prepare_key_paths()

        if self.private_path and self.public_path:
            return

        try:
            p12_path = self.config_obj[self.profile]["p12_key_store"]
            self._handle_log_msg("info",f"attempting to extract p12 private and public key from [{p12_path}].")
            with open(p12_path, 'rb') as f:
                p12_data = f.read()
            
            # Load the p12 keystore
            private_key, certificate, _ = serialization.pkcs12.load_key_and_certificates(
                p12_data,
                self.p12p.encode('utf-8'),
                default_backend()
            )
            
            self.private_key = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )

            public_key = certificate.public_key()
            self.public_key = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
        
        except Exception as e:
            self._handle_log_msg("error",f"unable to extract p12 private and public key from [{p12_path}] with error [{e}].")
            self.error_messages.error_code_messages({
                "line_code": "invalid_passphrase",
                "error_code": "crylib-207",
                "extra": f"{e}",
                "extra2": "wrong"
            })


if __name__ == "__main__":
    print("This module is not designed to be run independently, please refer to the documentation")