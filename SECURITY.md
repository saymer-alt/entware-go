# Security Policy

`SECURITY.md` documents coordinated disclosure; it **does not enable** GitHub Private Vulnerability Reporting. The availability of that feature must be verified separately.

## Supported scope

The actively maintained fork workflows and IPK packages published in the rolling [`latest`](https://github.com/saymer-alt/entware-go/releases/tag/latest) release; package freshness and security support are best-effort. The repository is a fork, not an independent upstream security authority for Entware, Mihomo or WARPSCOUT.

GitHub Actions supply chain, package provenance, signatures/checksums where implemented, the shared rolling release publication and the project's own packaging/install scripts. Bugs in packaged upstream software should also be reported to the respective upstream maintainers.

## Report a vulnerability privately

1. Visit the repository's [Security Advisories](https://github.com/saymer-alt/entware-go/security/advisories).
2. If the **Report a vulnerability** button is present, use it to provide a private report.
3. If that button is absent, **do not submit technical details of the vulnerability in a public issue or pull request**. You may open an Issue titled **Request private security contact**, with only a general non-sensitive subject and a request for a private communication channel. This is not itself a private reporting channel.

There is no verified security contact email published by this project. Do not send secrets to contacts you have not confirmed.

## What to include in a private report

- Affected software/package version and environment.
- Potential impact and minimum reproduction with synthetic, non-secret fixtures.
- Relevant redacted evidence and uncertainty/limits of testing.
- Suggested mitigation, where available.

Do **not** attach GitHub Actions secrets, release or registry tokens, signing keys, private package-feed credentials, unpublished source artifacts, personal information or confidential infrastructure details. Share only redacted build logs, public release links, checksums and synthetic reproductions.

## Disclosure process

Please coordinate public disclosure with maintainers before releasing exploit details. Responses and patches are best-effort; no fixed security SLA is promised. Vulnerabilities in third-party upstream components may require separate upstream disclosure.

Non-sensitive bugs and feature ideas belong in [Issues](https://github.com/saymer-alt/entware-go/issues/new/choose).
