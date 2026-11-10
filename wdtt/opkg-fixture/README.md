# Native opkg fixture

This builds the Entware-patched host package manager, not a router opkg binary. Pins are copied from Entware package/system/opkg and package/libs/libubox at the commit in pins.json. Both source commits and every original patch SHA256 are fixed. Patch bytes are base64 source in pins.json so Git whitespace normalization cannot alter upstream context; build_opkg_fixture.py decodes and verifies each patch before applying it.

Dependencies: native GCC, CMake, Make, pkg-config, json-c development headers. These do not change the Entware SDK/Go toolchain used for WDTT clients. Build locally with `python3 wdtt/build_opkg_fixture.py /absolute/work/opkg-fixture`.

Only invoke this binary with a test-specific config and `-o /absolute/private/offline-root`. The regression has no force flags or feed URLs. It installs real target ELF payloads without executing them, tests repeat/upgrade/remove and wrong architecture/corrupt archive, and checks installed file hashes and preservation of foreign files/shared-directory modes. Offline opkg skips maintainer scripts; the exact read-only preinst is separately executed with IPKG_INSTROOT under sh and BusyBox ash. No target hardware or real reboot is inferred.
