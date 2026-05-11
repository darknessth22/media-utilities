"""Public verification key for installer-update signature checks.

The updater fetches Videl_Setup.exe.sig.json, verifies its Ed25519 signature
against this key, then verifies the installer sha256 + size match the manifest
before launching it. Generate the keypair with `cryptography` (Ed25519); keep
the private half in tools/private_key.pem (gitignored) and bake the public
half here, urlsafe-base64, no padding.
"""
PUBLIC_KEY_B64 = "nITwJIU2qINUWwpb7XAlhYdevmliOPM06JAf53ftKZg"
