# Zadanie 2 — siatki H3

Źródło: `data/powiat.shp`, **powiat Warszawa**, kod 1465. To obszar faktycznie
zapisany w danych z zajęć 1; nie powiat sochaczewski wymieniony przy autorze w README.

## Uruchamianie

GitHub → Actions → **Load H3 Grids** → Run workflow → gałąź `main`.
Domyślne rozdzielczości: `6,7,8,9`. Workflow kolejno zasila `env-test`, `env-qa`
i `main`. Bazy muszą działać, a runner musi mieć dostęp do lokalnego Dockera.
Każdy job korzysta z sekretów swojego środowiska: `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_DB`. Hasła nie są zapisane w kodzie.
Połączenie odbywa się przez osobną sieć Compose danego środowiska, na porcie 5432.

Skrypt i dane są kopiowane do obrazu podczas budowania. Nie używamy podmontowania
ścieżki workspace runnera: runner działa w kontenerze, a daemon Dockera na hoście.

## Wynik w każdej bazie

Aktualizacja BDOT: loader zapisuje teraz geometrie w **EPSG:2180** i wykonuje
przycięcia w tym układzie. Starsze tabele 4326 są migrowane podczas uruchomienia.
Migrację w ramach rozszerzenia BDOT wykonano tylko w `env-test`.
Zasady analizy i widoki wizualizacyjne EPSG:3857 opisano w [bdot.md](bdot.md).

- `grid.powiat` — połączona geometria obszaru źródłowego w EPSG:2180.
- `grid.h3_cells` — komórki wszystkich wybranych rozdzielczości:
  `resolution`, `h3_index`, `geom` (pełny heksagon), `geom_clipped`
  (część w granicach powiatu), `area_m2` (pole części przyciętej w EPSG:2180).
- Klucz `(resolution,h3_index)` uniemożliwia duplikaty; indeksy GiST wspierają
  zapytania przestrzenne.

H3 otrzymuje współrzędne WGS84 po transformacji z CRS pliku `.prj`.
Tryb `overlap` uwzględnia komórki na granicy nawet wtedy, gdy ich środki leżą
poza powiatem. Pełne komórki zachowują kształt H3, a części przycięte pokrywają
obszar powiatu, zachowując otwory. Rozdzielczości są generowane niezależnie.
Im większy numer H3, tym mniejsze komórki. Funkcja overlap pochodzi z API
eksperymentalnego H3; wersja pakietu jest przypięta, a pokrycie sprawdzane testami.

Ponowne wykonanie zastępuje wyłącznie wygenerowaną zawartość `grid.h3_cells`
i aktualizuje `grid.powiat` w jednej transakcji. Błąd powoduje rollback.
Inne tabele nie są modyfikowane. Wybór innych rozdzielczości zastępuje dotychczasowy
zestaw, nie dopisuje go. Blokada transakcyjna chroni przed równoległym importem.

## Kontrola wyniku

```sql
SELECT resolution, count(*) AS komorki,
       count(*) FILTER (WHERE NOT ST_IsValid(geom_clipped)) AS bledne,
       round(sum(area_m2)::numeric / 1000000, 3) AS powierzchnia_km2
FROM grid.h3_cells
GROUP BY resolution ORDER BY resolution;
```

Oczekiwane liczby dla obecnego pliku: 6 → 28, 7 → 142, 8 → 850, 9 → 5575.
Łącznie 6595 komórek na środowisko. Powierzchnia przyciętej siatki na każdym
poziomie wynosi około 516,723 km². Niewielkie różnice pól między poziomami wynikają
z segmentacji krawędzi przy transformacji do układu metrycznego.

Przykład warstwy do wyświetlenia w QGIS:

```sql
SELECT h3_index, geom_clipped AS geom
FROM grid.h3_cells WHERE resolution = 8;
```

Nie sumuj pól komórek z różnych rozdzielczości — każdy poziom pokrywa ten sam powiat.

## Generator poza bazą

`app/python/h3_generator.py` może również zapisać przyciętą siatkę jako GeoJSON:

```sh
python app/python/h3_generator.py --input data/powiat.shp \
  --resolutions 6,7,8,9 --output grid.geojson
```

Wymaga GDAL oraz pakietów z `app/requirements.txt`; kompletne środowisko
zawiera obraz z `docker/python/Dockerfile`.

## Testy

Obraz uruchamia testy generatora poleceniem:
`python -m unittest discover -s /app/tests -v`.
Sprawdzane są: rzeczywisty powiat, bardzo mały obszar, otwory, rozłączne poligony,
identyfikatory H3, współrzędne, pokrycie i błędne rozdzielczości.
Test bazodanowy wymaga `RUN_DB_INTEGRATION=1` oraz danych połączenia do bazy
testowej. Sprawdza powtarzalność oraz zachowanie poprzednich danych po błędzie.
Loader przed zatwierdzeniem sam sprawdza poprawność geometrii i względny błąd
pokrycia obszaru (maksymalnie 0,001%).
