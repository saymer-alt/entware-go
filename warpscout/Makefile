# SPDX-License-Identifier: MIT
#
# WARPSCOUT upstream publishes a CGO-free, UPX-compressed Linux/ARM64 binary.
# The current Entware SDK (v2026.07.04) ships Go 1.26.1 while WARPSCOUT v0.16.0
# requires Go 1.26.3, so this package intentionally repacks the official ARM64
# release asset instead of weakening the repository's GOTOOLCHAIN=local policy.

include $(TOPDIR)/rules.mk

PKG_NAME:=warpscout
PKG_VERSION:=0.16.0
PKG_RELEASE:=1

PKG_SOURCE:=warpscout_$(PKG_VERSION)_linux_arm64.tar.gz
PKG_SOURCE_URL:=https://github.com/vernette/warpscout/releases/download/v$(PKG_VERSION)
PKG_HASH:=261ef88a1ac6eb405ea2d11d80fcce823913ae1faaff9cdc1dff4465c516483d
UNPACK_CMD=tar -xzf $(DL_DIR)/$(PKG_SOURCE) -C $(1)

PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/warpscout
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Web Servers/Proxies
  TITLE:=Cloudflare WARP endpoint scanner (ARM64)
  URL:=https://github.com/vernette/warpscout
  EXTRA_DEPENDS:=ca-bundle
endef

define Package/warpscout/description
  WARPSCOUT scans Cloudflare WARP WireGuard, AmneziaWG and MASQUE endpoints
  from the local network and reports working edge nodes, latency and loss.
  This package is built from the official upstream Linux/ARM64 release asset.
endef

Build/Compile:=:

define Package/warpscout/install
	$(INSTALL_DIR) $(1)/opt/bin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/warpscout $(1)/opt/bin/warpscout
	$(INSTALL_DIR) $(1)/opt/etc/warpscout
endef

$(eval $(call BuildPackage,warpscout))
