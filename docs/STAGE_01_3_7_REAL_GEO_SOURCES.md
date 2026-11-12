# Этап 1.3.7: подключение спутникового источника ESA WorldCover

## Источник и права

- ESA WorldCover 2021 v200, 10 м, GeoTIFF COG, EPSG:4326.
- Официальный каталог: https://esa-worldcover.org/en/data-access
- Лицензия: Creative Commons Attribution 4.0; обязательно указывать «© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium».
- WorldCover классифицирует **земной покров**, а не юридическую пригодность строительства. Класс 80 = постоянная вода; класс 50 = застроенные территории. Отсутствие класса 80 НЕ означает, что клетка безопасна.
- COP-DEM-GLO-30 требует проверки права доступа к конкретному сервису, поэтому DEM автоматически не скачиваем. Официальное описание: https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM.html

## Что реализовано

- `server/basheco/worldcover_source.py`: автономное чтение локального, отдельно полученного GeoTIFF через опциональный `rasterio`. CRS преобразуется из EPSG:32640; для каждой 6-метровой клетки проверяются пересекающиеся пиксели (all_touched).
- Клетки с классом воды 80 получают `water=blocked`. Другие классы и непокрытые пиксели получают `water=unknown`, а не ложное разрешение.
- `geography_audit.py --pilot-worldcover /path/to/ESA_WorldCover_10m_2021_v200_....tif` запускает проверку только Михайловки по локальному растру. Без параметра сохраняется прежнее поведение.
- Слой `terrain`, `protected_area` и `land_rights` остаётся unknown. `safe_to_publish` остаётся false.
- Никакой сетевой загрузки больших растров, никакого деплоя, никаких изменений production-БД. Растр не добавляется в Git.

## Запуск в изолированном окружении

```sh
python -m venv /tmp/basheco-geo-venv
/tmp/basheco-geo-venv/bin/pip install rasterio numpy
PYTHONPATH=server /tmp/basheco-geo-venv/bin/python -m basheco.geography_audit \
  --pilot-worldcover /path/to/verified/ESA_WorldCover_10m_2021_v200_tile.tif \
  --output build/pilot-geography-audit.json
```

Проверены 2 теста адаптера, включая чтение синтетического GeoTIFF в отдельном контейнере с rasterio/numpy и системной библиотекой libexpat1. Реальное скачивание и контроль лицензии/контрольной суммы растра ещё не выполнены. Для уклонов нужен отдельный DEM-адаптер с учётом разрешения 30–90 м, nodata и ошибки измерения. Официальные юридические слои необходимо получать и проверять отдельно. Синтетический тест не подтверждает работу на настоящем тайле ESA.