# SPDX-License-Identifier: GPL-2.0-only
#
# Copyright (C) 2024-2026 Entware

include $(TOPDIR)/rules.mk

PKG_NAME:=fzf
PKG_VERSION:=0.74.3
PKG_RELEASE:=1

PKG_SOURCE_PROTO:=git
PKG_SOURCE_VERSION:=15f64c492a08f0840b81540c7d1de35737448086
PKG_SOURCE_URL:=https://github.com/junegunn/fzf
PKG_MIRROR_HASH:=7c5790cf5f9fd1c77f0ed3f6dfa36319149a149116110cf0ccaa0b78de30960d

PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=LICENSE
PKG_MAINTAINER:=Entware team, https://entware.net

PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/golang.mk

define Package/fzf/Default
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=A command-line fuzzy finder
  URL:=https://github.com/junegunn/fzf
  PROVIDES:=fzf
endef

define Package/fzf
  $(call Package/fzf/Default)
  VARIANT:=hf
  DEFAULT_VARIANT:=1
endef

define Package/fzf_nohf
  $(call Package/fzf/Default)
  VARIANT:=nohf
  DEPENDS:=@arm
endef

define Package/fzf/description
  fzf is a general-purpose command-line fuzzy finder.
endef

Package/fzf_nohf/description=$(Package/fzf/description)

GO_LDFLAGS += \
	-X 'main.version=$(PKG_VERSION)' \
	-X 'main.revision=$(COMMIT_SHORT)'

define Package/fzf/install
	$(INSTALL_DIR) $(1)/opt/sbin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/bin/fzf $(1)/opt/sbin
endef

Package/fzf_nohf/install=$(Package/fzf/install)

$(eval $(call BuildPackage,fzf))
$(eval $(call BuildPackage,fzf_nohf))
