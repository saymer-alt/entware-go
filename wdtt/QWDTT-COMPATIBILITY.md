# qwdtt:// compatibility — research only, Phase 5

Evidence is the pinned upstream/fork source, not a connection to a public
server. The owner reports Germany/Netherlands/WARP profiles from @kfwlrus;
their live configuration, server revisions, permission and availability have
not been verified. No real URI/password/profile was copied or fetched. No
importer or runtime guard was changed. No remote server connection was made.

## Source contract

At upstream base1110a75 / maintained fork ff88cae:

- Android `SubscriptionImport.kt`, parseQwdttUri (169-190), parses name/peer/
  hashes/workers/port/pass, password alias; defaults workers18 and port9000.
  Missing hashes selects Android global hashes. This is application state,
  not a self-contained credential export.
- `TunnelManager.kt` (325-405) chooses account/anonymous from application
  settings, bounds workers, passes all normalized hashes, sets loopback listen,
  password/device and VPN/SOCKS mode. Those settings are absent from the URI.
- `go_client/group.go`: workersPerGroup=9; ParseHashes (256+) splits comma,
  semicolon and whitespace, normalizes VK links, deduplicates.
- `go_client/main.go` (247-264): account workers clamp1..4; anonymous workers
  clamp to at least9 and round down to a multiple of9 (cap108).
- `go_client/lab_security.go`: private JSON only; account1..4 with credentials
  file; anonymous exactly12; password minimum16; literal IPv4 peer; listen
  127.0.0.1 with nonzero port. It forces existing `mode=vpn` and excludes the
  AWG daemon entry.
- `go_client/protocol.go`: GETCONF is `GETCONF:port|device|password`, AUTH is
  `AUTH:device|password`. WRAP key derives from the same password. GETCONF
  returns WireGuard config; the local UDP path carries WG packets.

Primary source links:
[Android importer](https://github.com/saymer-alt/proxy-turn-vk-android/blob/ff88cae7184561fe901e6e6a64f983ac6dd62980/app/src/main/java/com/wdtt/client/SubscriptionImport.kt),
[Android pipeline](https://github.com/saymer-alt/proxy-turn-vk-android/blob/ff88cae7184561fe901e6e6a64f983ac6dd62980/app/src/main/java/com/wdtt/client/TunnelManager.kt),
[client policy](https://github.com/saymer-alt/proxy-turn-vk-android/blob/ff88cae7184561fe901e6e6a64f983ac6dd62980/go_client/lab_security.go),
[protocol](https://github.com/saymer-alt/proxy-turn-vk-android/blob/ff88cae7184561fe901e6e6a64f983ac6dd62980/go_client/protocol.go).

## Mapping and blockers

| URI field | Proposed private JSON mapping | Current compatibility |
|---|---|---|
| name | Local display metadata only | No runtime field; never a path or log secret |
| peer | peer | Only literal IPv4 host:port passes current policy; hostname/IPv6 needs separate decision |
| hashes | vk | Existing parser supports multiple values; URI must URL-encode delimiters; missing values must not silently use unavailable Android global state |
| workers9/16/18 | workers | All rejected by current lab gate: account max4, anonymous exactly12 |
| port | listen127.0.0.1:port | Local endpoint, not remote peer port; reserve/check occupancy, match Mihomo endpoint |
| pass/password | password | Private JSON0600 in0700; require>=16 and no wire delimiters; never argv/env/URL logs |
| VK auth/credentials | Separate owner choice and private file | URI hashes alone are not TURN username/password or a VK account login |
| device binding | Explicit private stable test device | URI does not carry Android's device ID or a server binding authorization |
| WG/VPN mode | Explicit separate test setting | Current standalone `vpn` is WG-over-local-UDP; URI carries no mode selector |

Important existing mismatch: lab anonymous12 passes validation but upstream
normalization yields9 effective workers. Original anonymous requests9/16/18
would yield9/9/18; account requests clamp to4. These semantics are not preserved
by blindly importing into the lab profile. The Android name workersPerHash does
not alone prove a per-hash multiplier; inspect actual worker group/hash
selection and credential allocation before resource budgeting. Do not raise
limits just to make a profile parse.

Account credentials use `vk_account.go` private-file path; anonymous uses VK
credential acquisition paths (`creds.go`/`creds_vkcalls.go`), with quota,
expiry/captcha/service dependencies. A profile cannot prove credential
availability. Existing local synthetic TURN acceptance bypasses that external
acquisition and therefore proves neither VK nor public-server compatibility.

AUTH/GETCONF wire format is source-compatible in our verified pair, but remote
public servers may use other revisions/policies, device bindings and expiry.
WARP is a server-side label, not a new URI/client mode. The URI does not prove
which upstream WireGuard routing that server returns. Treat all three public
profiles as NOT TESTED, not as incompatible protocol by assumption.

## Proposed implementation, separately authorized

1. Offline-only preview parser: exact scheme/host, bounded input length,
   URL decode once, reject duplicate/security-critical/unknown query keys,
   controls/ambiguous ports. No DNS, HTTP, TURN or server contact while parsing.
2. Show redacted peer, hash count, requested/effective worker count, local port,
   missing auth/device/mode choices and blockers. Never log/persist original
   URI, pass or hashes in CI, Issues or telemetry.
3. Require explicit account/anonymous selection, credential file when needed,
   owner-approved worker/resource profile and mode. No silent clamping or
   weakening the current admission. Resolve anonymous12->9 separately with
   measured RSS/CPU and synthetic protocol regression.
4. Emit only a new private JSON atomically0600 into verified0700 directory;
   refuse overwrite/symlinks, preserve existing configs. Parsing does not start
   a client or change routes/DNS/Mihomo.
5. Synthetic fixtures only: encoded multiple hashes, empty/duplicate keys,
   malformed host/IPv6/hostname, port0/65536/occupied, short/delimited password,
   workers9/16/18 per both auth modes, effective count, missing credentials,
   wrong device/expired/revoked AUTH, WG GETCONF and secret-free failures.
6. After owner approval, one disposable/public test endpoint at a time,
   bounded workers/time, captured redacted evidence and isolated SOCKS-only
   Mihomo without DIRECT fallback. No scanning or bulk connection.

The decision is to keep the importer and runtime guards unchanged now and track
this as acceptance/design work in entware-go#13 and the linked fork issue.

Tracking: [entware-go#13](https://github.com/saymer-alt/entware-go/issues/13), [fork#1](https://github.com/saymer-alt/proxy-turn-vk-android/issues/1).
