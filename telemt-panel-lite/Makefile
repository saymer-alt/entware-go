# SPDX-License-Identifier: MIT
# Unofficial ARM64 Entware packaging of the unmodified upstream Panel Lite binary.
# Panel 1.0.0-rc.3 requires Go 1.27 to build from source; use the official static release.

include $(TOPDIR)/rules.mk

PKG_NAME:=telemt-panel-lite
# Use tilde so the RC sorts older than a future stable 1.0.0 in opkg.
PKG_VERSION:=1.0.0~rc.3
PKG_RELEASE:=1

PKG_SOURCE:=telemt-panel-lite-aarch64-linux-musl.tar.gz
PKG_SOURCE_URL:=https://github.com/amirotin/telemt_panel/releases/download/v1.0.0-rc.3
PKG_HASH:=bf8f6160240521653d6abb02f953794aa1eab526b8f30e5682f69c07f17ed271
UNPACK_CMD=tar -xzf $(DL_DIR)/$(PKG_SOURCE) -C $(1)

PKG_LICENSE:=MIT
PKG_MAINTAINER:=Unofficial Entware package (saymer-alt)
PKG_BUILD_PARALLEL:=0

# Preserve the byte-identical official Go release binary. Entware's default
# rstrip.sh rewrites Go ELF files and breaks the upstream SHA256 identity check.
# This disables stripping for this recipe only; no global SDK settings change.
RSTRIP:=:

include $(INCLUDE_DIR)/package.mk

define Package/telemt-panel-lite
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Web Servers/Proxies
  TITLE:=TeleMT Panel 1.0 RC3 Lite web UI (ARM64, unofficial)
  URL:=https://github.com/amirotin/telemt_panel
  CONFLICTS:=telemt-panel
  EXTRA_DEPENDS:=ca-bundle
endef

define Package/telemt-panel-lite/description
  Unmodified upstream ARM64 static TeleMT Panel 1.0.0-rc.3 Lite build.
  Memory-only observability history; no SQLite. TeleMT is installed separately.
  No configuration, credentials, init script or network listeners are created.
endef

Build/Compile:=:

define Package/telemt-panel-lite/install
	$(INSTALL_DIR) $(1)/opt/bin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/telemt-panel $(1)/opt/bin/telemt-panel
	$(INSTALL_DIR) $(1)/opt/share/licenses/telemt-panel
	$(INSTALL_DATA) ./files/LICENSE $(1)/opt/share/licenses/telemt-panel/LICENSE
	$(INSTALL_DATA) ./files/THIRD_PARTY_NOTICES.md $(1)/opt/share/licenses/telemt-panel/THIRD_PARTY_NOTICES.md
endef

$(eval $(call BuildPackage,telemt-panel-lite))
