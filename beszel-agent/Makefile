# SPDX-License-Identifier: GPL-2.0-only
#
# Copyright (C) 2026 Entware

include $(TOPDIR)/rules.mk

PKG_NAME:=beszel-agent
PKG_VERSION:=0.18.7
PKG_RELEASE:=1

PKG_SOURCE_PROTO:=git
PKG_SOURCE_VERSION:=v$(PKG_VERSION)
PKG_SOURCE_URL:=https://github.com/henrygd/beszel
PKG_MIRROR_HASH:=64b66bf9c5466befdc7ac1e55cbc8a3934d84f2a344f19ef2432c49bb1b9eaa7

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
	$(STAGING_DIR_HOST)/bin/upx -9 --lzma $(PKG_INSTALL_DIR)/bin/beszel-agent
endef

define Package/beszel-agent
  SECTION:=net
  CATEGORY:=Network
  TITLE:=Beszel monitoring agent
  URL:=https://github.com/henrygd/beszel
  DEPENDS:=+ca-certificates
endef

define Package/beszel-agent/description
  Lightweight server monitoring agent for Beszel hub
endef

GO_TARGET:=./internal/cmd/agent

GO_LDFLAGS += \
	-X 'github.com/henrygd/beszel.Version=v$(PKG_VERSION)'

define Package/beszel-agent/install
	$(INSTALL_DIR) $(1)/opt/sbin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/bin/agent $(1)/opt/sbin/beszel-agent

	$(INSTALL_DIR) $(1)/opt/etc/init.d
	$(INSTALL_BIN) ./files/S99beszel-agent $(1)/opt/etc/init.d/S99beszel-agent

	$(INSTALL_DIR) $(1)/opt/etc
	$(INSTALL_CONF) ./files/beszel-agent.conf $(1)/opt/etc/beszel-agent.conf
endef

define Package/beszel-agent/conffiles
/opt/etc/beszel-agent.conf
endef

$(eval $(call BuildPackage,beszel-agent))
