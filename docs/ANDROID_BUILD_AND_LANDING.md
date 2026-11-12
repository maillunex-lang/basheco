# BASHECO: тестовая Android-сборка и лендинг

Дата: 12.11.2026. **Опубликована отладочная сборка, не production release.**

## Подготовленное окружение на Lunex

- Godot **4.6.stable.official.89cea1439**: `/opt/godot/4.6-stable/Godot_v4.6-stable_linux.x86_64`.
- Официальные export templates Godot 4.6: `/root/.local/share/godot/export_templates/4.6.stable/`.
- Android SDK: `/opt/android-sdk`, platform-tools, Build Tools 35/36, platforms 35/36.
- Java SDK: `/usr/lib/jvm/java-17-openjdk-amd64`.
- Debug keystore: `/root/.android/debug.keystore` (права 0600). Защищённая копия на том же VPS: `/root/basheco-backups/signing/basheco-navigation-debug.keystore`. **Никогда не добавлять keystore, пароли или закрытые ключи в GitHub.** Копия на том же VPS не заменяет внешнюю резервную копию.
- `/root/.config/godot/editor_settings-4.6.tres` содержит пути к SDK/JDK и отладочному keystore.
- Прежний Godot 4.8 beta3 оставлен без изменений. Контейнеры API/БД не пересоздавались.

## Воспроизведение сборки

Работать с **чистой копией актуального main**, не в рабочем `/opt/basheco`:

```sh
git clone --branch main https://github.com/maillunex-lang/basheco.git /tmp/basheco-android-build
cd /tmp/basheco-android-build
GODOT_SILENCE_ROOT_WARNING=1 /opt/godot/4.6-stable/Godot_v4.6-stable_linux.x86_64 --headless --path client --editor --quit
GODOT_SILENCE_ROOT_WARNING=1 /opt/godot/4.6-stable/Godot_v4.6-stable_linux.x86_64 --headless --path client -s tests/navigation.gd
GODOT_SILENCE_ROOT_WARNING=1 /opt/godot/4.6-stable/Godot_v4.6-stable_linux.x86_64 --headless --path client -s tests/smoke.gd
GODOT_SILENCE_ROOT_WARNING=1 /opt/godot/4.6-stable/Godot_v4.6-stable_linux.x86_64 --headless --path client --export-debug Android /tmp/BASHECO-navigation-test.apk
/opt/android-sdk/build-tools/35.0.0/apksigner verify --verbose --print-certs /tmp/BASHECO-navigation-test.apk
/opt/android-sdk/build-tools/35.0.0/aapt dump badging /tmp/BASHECO-navigation-test.apk
sha256sum /tmp/BASHECO-navigation-test.apk
```

Параметры опубликованной сборки: package `org.basheco.game`, `versionCode=2`, `versionName=0.1.1-nav-test`, min SDK 24, target SDK 35, ARM64. Размер 27 861 304 байт, SHA256 `85480a253ec777102964b6741d8691f88d487d8a0522a1b814e564227f32c647`.

## Публикация на сайте

- Сайт: `https://rikagro.ru/`.
- Новая сборка: `https://rikagro.ru/downloads/BASHECO-navigation-test.apk`.
- Предыдущая тестовая сборка сохранена без изменений: `/var/www/rikagro-game/downloads/BASHECO-test.apk`.
- Nginx разрешает **только** два явно названных APK; общий путь `/downloads/` закрыт.
- Ссылка на главной странице обновлена, добавлено предупреждение о несовместимой подписи.
- Резервные копии конфигурации Nginx и лендинга: `/root/basheco-backups/nginx/`, `/root/basheco-backups/landing/`.
- После публикации проверены HTTP 200 для лендинга, нового и старого APK, а также `/basheco/api/health`; оба контейнера были healthy.

## Важно: подпись и обновления

**Подпись старой и новой сборки различается.** SHA256 сертификата нового debug APK:
`c4d731bf72cad32c9f94e19dc61c5ca6cc6ebc6e29deb11490093203bdfc1720`.
Старый APK подписан сертификатом `79e0502de889422ea05faafe2a8a200a32ae532c2852a9b9f3a9919c6ed22a11`.
Поэтому Android **не сможет обновить старую установку новым APK**. Пользователь должен удалить старую версию, при этом локальные данные приложения могут быть потеряны. Это ограничение тестового канала.

**Нельзя выпускать production APK с этим debug keystore.** Для стабильного канала нужен отдельный постоянный release key, безопасное хранение и резервирование, повышение `versionCode` при каждом обновлении, проверка установки поверх предыдущего APK. Самообновление внутри приложения и проверка версий с сервера ещё **не реализованы**. Перед публичным релизом также нужны тесты на реальном Android, проверка сетевых запросов, интерфейса и производительности.

## Результат тестирования

Godot 4.6 stable: `BASHECO_NAVIGATION_OK`, `BASHECO_GODOT_SMOKE_OK`, `BASHECO_GRID_PARITY_OK`. Экспорт подписан и проверен `apksigner`; архив содержит `assets/data/admin_navigation.json`. На физическом смартфоне APK ещё не проверен.
