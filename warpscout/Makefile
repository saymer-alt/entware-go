# SPDX-License-Identifier: MIT
#
# WARPSCOUT package for Entware aarch64 targets.

include $(TOPDIR)/rules.mk

PKG_NAME:=warpscout
PKG_VERSION:=0.16.0
PKG_RELEASE:=1

PKG_SOURCE_PROTO:=git
PKG_SOURCE_VERSION:=v$(PKG_VERSION)
PKG_SOURCE_URL:=https://github.com/vernette/warpscout
# Bootstrap value: the PR workflow patches this to "skip" only inside CI.
# Replace with the real mirror hash learned from the first successful SDK download before merge.
PKG_MIRROR_HASH:=0000000000000000000000000000000000000000000000000000000000000000

PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=LICENSE

PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/golang.mk

define Build/Install
	$(call GoPackage/Install)
	mkdir -p $(STAGING_DIR_HOST)/bin
	wget -q -O /tmp/upx.tar.xz https://github.com/upx/upx/releases/download/v5.1.1/upx-5.1.1-amd64_linux.tar.xz
	tar -xJf /tmp/upx.tar.xz -C /tmp
	cp /tmp/upx-5.1.1-amd64_linux/upx $(STAGING_DIR_HOST)/bin/upx
	chmod +x $(STAGING_DIR_HOST)/bin/upx
	$(STAGING_DIR_HOST)/bin/upx -9 --lzma $(PKG_INSTALL_DIR)/bin/warpscout
endef

define Package/warpscout
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Web Servers/Proxies
  TITLE:=Cloudflare WARP endpoint scanner
  URL:=https://github.com/vernette/warpscout
  EXTRA_DEPENDS:=ca-bundle
endef

define Package/warpscout/description
  WARPSCOUT scans Cloudflare WARP WireGuard, AmneziaWG and MASQUE endpoints
  from the local network and reports working edge nodes, latency and loss.
endef

GO_TARGET:=./

GO_LDFLAGS += \
	-X 'main.version=$(PKG_VERSION)'

define Package/warpscout/install
	$(INSTALL_DIR) $(1)/opt/bin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/bin/warpscout $(1)/opt/bin/warpscout
	$(INSTALL_DIR) $(1)/opt/etc/warpscout
endef

$(eval $(call BuildPackage,warpscout))
