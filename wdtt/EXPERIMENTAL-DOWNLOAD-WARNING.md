# ⚠️⚠️⚠️ WDTT — эксперимент, допуск закрыт ⚠️⚠️⚠️

Личный некоммерческий публичный исследовательский проект владельца. Некоммерческий статус и надпись «на свой риск» не предоставляют права на чужой код.

**До подтверждения licensing/distribution gates новые ELF/IPK не публикуются в публичных Actions artifacts, Releases, latest или Entware feed.** Это относится и к owner-test пакетам. `owner_test_ipk.py` теперь соблюдает общий admission; `verify_quarantine.py` только приватно проверяет реальные архивы с запрещающим preinst и уничтожает их после проверки.

Это не утверждение, что все чужие ранее созданные artifacts удалены: Phase3 не изменяет прошлые workflow runs/artifacts. Текущий workflow сохраняет только текстовые доказательства. Исторические downloadable материалы не становятся лицензионно одобренными вследствие warning.

Реальный VK, Keenetic ABI/RAM/init/reboot и внешние leak/recursion tests ещё не приняты. Не устанавливать WDTT в рабочую сеть; не менять домашний Keenetic или существующие Mihomo/KAS службы. Следующий разрешённый шаг владельца — read-only preflight отдельного стенда.

Возможная будущая выдача install-ready пакетов требует complete notices/corresponding source и проверенной provenance, security/installer review, точного hardware preflight и отдельного разрешения владельца. Отсутствующий fhttp license scope не закрывается этим документом.
