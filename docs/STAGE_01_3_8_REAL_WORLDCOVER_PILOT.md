# Этап 1.3.8: первый реальный растр ESA WorldCover, Михайловка

Дата: 2026-11-12. Только изолированный геоанализ, без деплоя.

## Подтверждённый источник

ESA WorldCover 2021 v200, тайл `N54E054`, слой Map, Cloud Optimized GeoTIFF. Официальный адрес:
https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N54E054_Map.tif

Скачанный файл: 67 938 461 байт. SHA-256:
`77dfa16f2ad2cbdec2ee2977c7475d69fb54a09c11f7d713bae3ca61e8f3f291`.

© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium. CC BY 4.0.

## Результат реального запуска

Изолированный контейнер Python 3.13 + rasterio + numpy + pyproj, локально скачанный тайл и текущая ветка main (до этого коммита).

```
PYTHONPATH=server python -m basheco.geography_audit \
  --pilot-worldcover /geo/ESA_WorldCover_10m_2021_v200_N54E054_Map.tif \
  --output /tmp/pilot-audit.json
```

Результат: 252 кандидата в общем предварительном аудите; для Михайловки 127 занятых клеток; по данным ESA WorldCover класс постоянной воды 80 не обнаружен в этих клетках. В отчёте `blocked_checks=0`, `unknown_checks=508` (127 клеток × 4 обязательных слоя), `safe_to_build=false`, `safe_to_publish=false`. Сводка и контрольная сумма сохранены в `docs/data/pilot_worldcover_2021_observation.json`.

**Важно:** `water=unknown` даже для пикселей, где нет класса 80. Это корректно: классификация земного покрова 10 м не доказывает отсутствие узких ручьёв, заболоченности и сезонных паводков. Отсутствуют достоверные DEM, границы охраняемых территорий и данные о правах на землю.

## Следующий шаг

Добавить проверяемый адаптер DEM с расчётом уклонов и nodata, затем дополнительные источники гидрографии (включая сезонные водотоки), юридических ограничений и кадастровых данных. Разрешение на публикацию не выдавать до отдельной валидации и проверки полноты данных.

В production ничего не менялось. Большой GeoTIFF не включён в GitHub.