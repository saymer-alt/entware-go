# SPDX-License-Identifier: LicenseRef-TELEMT-3.3
#
# Unofficial Entware packaging of the unmodified upstream ARM64 MUSL binary.
# Never compile against the Entware Go toolchain; TeleMT is a Rust application.

include $(TOPDIR)/rules.mk

PKG_NAME:=telemt
PKG_VERSION:=3.5.17
PKG_RELEASE:=1

PKG_SOURCE:=telemt-aarch64-linux-musl.tar.gz
PKG_SOURCE_URL:=https://github.com/telemt/telemt/releases/download/$(PKG_VERSION)
PKG_HASH:=c80b0159b41cf410b2a87cf62676d67a16a537bd7207602b60dd9ce56e14d1f6
UNPACK_CMD=tar -xzf $(DL_DIR)/$(PKG_SOURCE) -C $(1)

PKG_LICENSE:=LicenseRef-TELEMT-3.3
PKG_MAINTAINER:=Un-official Entware package (saymer-alt)
PKG_BUILD_PARALLEL:=0

include $(INCLUDE_DIR)/package.mk

define Package/telemt
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Web Servers/Proxies
  TITLE:=TeleMT MTProto proxy (upstream ARM64 MUSL binary)
  URL:=https://github.com/telemt/telemt
  DEPENDS:=@aarch64
  EXTRA_DEPENDS:=ca-bundle
endef

define Package/telemt/description
  Unofficial Entware ARM64 package of upstream TeleMT, written in Rust.
  Packages the unmodified statically linked aarch64-musl release binary.
  No default credentials, configuration, init script or service activation.
endef

# Source is a one-file release tarball; there is no local compile.
Build/Compile:=:

define Package/telemt/install
	$(INSTALL_DIR) $(1)/opt/bin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/telemt $(1)/opt/bin/telemt
	$(INSTALL_DIR) $(1)/opt/share/licenses/telemt
	$(INSTALL_DATA) ./files/LICENSE $(1)/opt/share/licenses/telemt/LICENSE
endef

$(eval $(call BuildPackage,telemt))
