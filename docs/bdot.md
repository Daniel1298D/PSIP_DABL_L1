# BDOT10K — Warszawa, środowisko env-test

Źródło: oficjalna paczka GUGiK dla **powiatu Warszawa, TERYT 1465**:
https://opendata.geoportal.gov.pl/bdot10k/schemat2021/14/1465_GML.zip
Skorowidz WFS GUGiK wskazywał datę aktualizacji 2024-04-02. Granica analizy pochodzi
z dotychczasowego `data/powiat.shp`. Obiekty są mierzone wyłącznie w jej obrębie.

## Schematy i układy

- `bdot.ot_*` — wszystkie 73 klasy paczki, również klasy puste, geometrie EPSG:2180.
  Zachowane są identyfikatory i atrybuty źródłowe w kolumnie JSONB `attributes`.
- `bdot.layer_catalog` — nazwy klas i kolumn wynikowych, typ miary, jednostka,
  liczba obiektów, liczba napraw geometrii, URL i SHA256 paczki.
- `grid.powiat`, `grid.h3_cells` — granica i heksagony w EPSG:2180.
- `analysis.h3_7`, `analysis.h3_8`, `analysis.h3_9` — tabele wynikowe w EPSG:2180.
- `viz.h3_7`, `viz.h3_8`, `viz.h3_9` — widoki wynikowe dla QGIS, geometria EPSG:3857.
  Transformacja dotyczy wyłącznie geometrii prezentacyjnej; wartości miar nie są
  przeliczane w Web Mercator.

H3 definiuje identyfikatory komórek na sferze, więc samo wyznaczenie identyfikatora
w bibliotece H3 wymaga współrzędnych geograficznych. Po wyznaczeniu pełnych granic
komórek następuje transformacja do EPSG:2180. Przycinanie, przecięcia, pomiary,
agregacje i zapis geometrii do tabel wykonywane są w 2180. Dotychczasowa siatka
testowa jest migrowana, zachowując identyfikatory H3. Inne środowiska nie są
modyfikowane przez workflow BDOT.

## Układ tabel

Jeden wiersz odpowiada jednemu heksagonowi. Kolumny początkowe to `id`, `h3_index`
oraz `geom`. Dalej znajduje się osobna kolumna dla każdej klasy, np.:

| Kolumna | Źródło | Miara |
|---|---|---|
| `bubd_a` | OT_BUBD_A, budynki | suma powierzchni części poligonów w komórce, m² |
| `skdr_l` | OT_SKDR_L, drogi | suma długości części linii w komórce, m |
| `oipr_p` | OT_OIPR_P | liczba punktów przypisanych do komórki |

Sufiksy: `_a` — powierzchnia, `_l` — linia, `_p` — punkt.
Nazwy pochodzą z rzeczywistych klas BDOT, dzięki czemu nie mylimy budynków
powierzchniowych (`bubd_a`) z obiektami punktowymi.

Wszystkie kolumny miar mają `NOT NULL DEFAULT 0`. Pusta klasa lub komórka bez
obiektów daje **0**. NULL występujące w oryginalnych atrybutach opisowych BDOT
pozostają w JSONB jako dane źródłowe; nie są miarami agregacji.

## Reguły agregacji

Najpierw każdy obiekt jest przycinany do granicy powiatu w EPSG:2180, a następnie
dzielony między komórki. Zapobiega to błędom numerycznym na granicy obszaru.

- Poligony: suma `ST_Area(ST_Intersection(obiekt,heksagon))`.
- Linie: suma długości przecięć. Odcinek leżący dokładnie na wspólnej granicy
  komórek przypisywany jest tylko do komórki o niższym `id`.
- Punkty: każdemu punktowi przypisana jest jedna komórka. Przy położeniu na
  granicy wygrywa niższy `id`. Dla MultiPoint liczone są poszczególne punkty.
- Obiekty różnych klas i nakładające się obiekty w tej samej klasie nie są
  wzajemnie odejmowane: mierzymy sumę obiektów, nie powierzchnię unii klasy.
- Każda rozdzielczość jest niezależną agregacją; nie sumujemy wyników między H3 7/8/9.

## Uruchomienie i kontrola

Actions → **Import and Aggregate BDOT Warsaw** → Run workflow (`main`).
Workflow korzysta wyłącznie z sekretów `env-test`. Paczka jest buforowana
w volume `psip-bdot-cache`; jej rzeczywisty SHA256 zapisuje się w bazie.
Import jest atomowy, podobnie jak publikacja wszystkich trzech tabel agregacji.
Niepowodzenie agregacji zachowuje poprzednie tabele wynikowe. Przy ponownym
imporcie nowe dane źródłowe i stare wyniki mogą istnieć do czasu zakończenia
agregacji; aktualność wyniku potwierdza udane całe wykonanie workflow.

Po każdej klasie program porównuje sumę miar z niezależnym pomiarem obiektów
przyciętych do całego powiatu. Zgodność punktów musi być dokładna, a tolerancja
długości/powierzchni wynosi max(0,01 jednostki, 0,00001% wartości).
Wyniki kontroli są w `analysis.validation`.

```sql
SELECT id,h3_index,bubd_a,skdr_l,oipr_p FROM analysis.h3_8 ORDER BY id LIMIT 20;
SELECT * FROM analysis.validation ORDER BY resolution,layer_name;
SELECT f_table_schema,f_table_name,f_geometry_column,srid FROM geometry_columns
WHERE f_table_schema IN ('bdot','grid','analysis','viz');
```

W QGIS wczytaj warstwę `viz.h3_8`, wybierz styl stopniowany według `bubd_a`
lub `skdr_l`. Tabela atrybutów zawiera komplet kolumn dla wszystkich klas.
