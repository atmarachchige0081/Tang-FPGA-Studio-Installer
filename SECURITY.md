# Security

Do not report security vulnerabilities in a public issue. Use GitHub's private
security-advisory reporting for this repository or the main Tang Primer FPGA
Studio repository.

Release installers are built in GitHub Actions, accompanied by SHA-256
checksums, and receive signed GitHub/Sigstore build-provenance attestations.
The dependency bootstrap pins upstream URLs and SHA-256 hashes and validates
the downloaded Zadig Authenticode signer before it can be launched.

The v1.1.0 installer does not yet have a trusted Windows Authenticode publisher
signature. Do not disable antivirus or SmartScreen globally to install it.
