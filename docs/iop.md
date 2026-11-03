# Normalizacja, wagi i IOP — env-test

Obliczenia wykonuje lokalny skrypt `app/python/calculate_iop.py`, a definicje
wag znajdują się w `app/config/iop_weights.json`. Lokalne obliczenia są
niezależne od publikacji kodu na GitHubie.

Wyniki są zapisane w PostgreSQL `localhost:5434`, baza `psip`:

| H3 | Tabela wynikowa w EPSG:2180 | Widok dla przyszłej wizualizacji w EPSG:3857 | Liczba komórek |
|---|---|---|---:|
| 7 | `analysis.iop_h3_7` | `viz.iop_h3_7` | 142 |
| 8 | `analysis.iop_h3_8` | `viz.iop_h3_8` | 850 |
| 9 | `analysis.iop_h3_9` | `viz.iop_h3_9` | 5575 |

Każda tabela ma 223 kolumny: `id`, `h3_index`, 73 trójki kolumn
`wartość`, `wartość_norm`, `wartość_waga`, następnie `iop` i `geom`.
Na przykład: `bubd_a`, `bubd_a_norm`, `bubd_a_waga`.
Kolumny każdej trójki są obok siebie fizycznie w tabeli i w widoku.
Geometrie i wartości źródłowe są identyczne jak w `analysis.h3_7/8/9`.
Dotychczasowe tabele agregacji są źródłem nowych tabel wynikowych.

## Normalizacja

`x_norm = x / max(x)`

Maksimum jest liczone ze wszystkich komórek tej samej rozdzielczości,
osobno dla każdej z 73 warstw. Nie odejmujemy minimum. Przykład: 5 i 10
dają 0,5 i 1,0, a dwie jednakowe dodatnie wartości dają obie 1,0.
Przy maksimum 0 cała kolumna znormalizowana ma wartość 0.
Wyniki nie są zaokrąglane przed liczeniem IOP.

Zachowujemy rodzaj wcześniejszej miary: poligony — m², linie — m,
punkty — liczba punktów. `bubd_a` jest powierzchnią budynków,
nie ich liczbą. Normalizacja jest bezwymiarowa.

## Wagi i interpretacja

Wybrano dydaktyczny wariant „pojazd wojskowy”. Wartości budynków -0,8,
lasu -0,8, jezior -1,0 i dróg +0,7 pochodzą od użytkownika. Wagę jezior
zastosowano do istniejącej zbiorczej klasy `ptwp_a` (wody powierzchniowe).
Pozostałe wagi są jawną propozycją do ćwiczenia, bez kalibracji do konkretnego
pojazdu. Każda reprezentacja geometryczna ma osobną pozycję w
`analysis.iop_criteria`, również wtedy, gdy jej waga wynosi 0.

| Reprezentacje — kolumny źródłowe | Waga |
|---|---:|
| `adja_a`, `adms_a`, `adms_p` | 0,0 |
| `bubd_a` | -0,8 |
| `buhd_a`, `buhd_l` | -0,8 |
| `buib_a`, `buib_l` | -0,6 |
| `buin_l` | 0,0 |
| `buit_a`, `buit_p` | -0,4 |
| `busp_a`, `busp_l` | -0,2 |
| `butr_l`, `butr_p` | -0,4 |
| `buuo_l` | -0,7 |
| `buwt_a`, `buwt_p` | -0,4 |
| `buzm_l` | -0,6 |
| `buzt_a`, `buzt_p` | -0,7 |
| `kuho_a`, `kuhu_a`, `kuko_a`, `kuko_p`, `kumn_a`, `kuos_a`, `kuoz_a`, `kupg_a`, `kupg_p`, `kupw_a`, `kusc_a`, `kusk_a`, `kuza_a` | 0,0 |
| `oikm_a`, `oikm_l`, `oikm_p` | 0,0 |
| `oimk_a` | -0,9 |
| `oior_a`, `oior_l`, `oior_p` | -0,1 |
| `oipr_l`, `oipr_p` | -0,4 |
| `oisz_a` | -0,8 |
| `ptgn_a` | -0,3 |
| `ptkm_a` | 0,0 |
| `ptlz_a` | -0,8 |
| `ptnz_a` | 0,0 |
| `ptpl_a` | +0,4 |
| `ptrk_a` | -0,5 |
| `ptso_a` | -0,6 |
| `pttr_a` | +0,2 |
| `ptut_a` | -0,4 |
| `ptwp_a` | -1,0 |
| `ptwz_a` | -0,7 |
| `ptzb_a` | -0,6 |
| `rtlw_l`, `rtpw_p` | 0,0 |
| `skdr_l`, `skjz_l` | +0,7 |
| `skpp_l` | 0,0 |
| `skrp_l` | +0,1 |
| `skrw_p` | +0,5 |
| `sktr_l` | -0,3 |
| `suln_l`, `supr_l` | 0,0 |
| `swkn_l`, `swrs_l` | -0,8 |
| `swrm_l` | -0,5 |
| `tcon_a`, `tcpk_a`, `tcpn_a`, `tcrz_a` | 0,0 |

Uzasadnienie każdej wagi jest w pliku JSON i w `analysis.iop_criteria.rationale`.
Waga 0 oznacza neutralny udział w tym modelu. Dotyczy m.in. granic administracyjnych,
statusu ochrony i funkcjonalnych zasięgów kompleksów, które nie wyznaczają same
w sobie fizycznej przeszkody. Sama długość warstwic/liczba punktów wysokościowych
nie daje nachylenia terenu; sama długość przeprawy nie określa nośności.

Nazwy i zakresy klas sprawdzono w schemacie XSD dołączonym do wykorzystanej paczki
GUGiK oraz w [katalogu BDOT10k z 2021 r.](https://eli.gov.pl/api/acts/DU/2021/1412/text/I/D20211412.pdf).
Katalog definiuje klasy obiektów; nie jest źródłem przyjętych wag.

## IOP

`iop = (x1_norm*w1 + x2_norm*w2 + ... + x73_norm*w73) / 73`

Dzielnik jest stały i obejmuje wszystkie 73 kryteria, również puste i z wagą 0.
Nie dzielimy przez sumę wag ani liczbę niezerowych kryteriów. Przeszkód nie
odwracamy przy normalizacji — ich ujemne wagi nadają znak wkładowi do IOP.
Wysokie IOP oznacza korzystniejszy bilans przy przyjętych wagach. IOP ma zakres
teoretyczny [-1,1], podczas gdy poszczególne normalizacje mają zakres [0,1].

To indeks względny dla Warszawy i konkretnej rozdzielczości H3. Nie jest
prawdopodobieństwem ani procentem przejezdności. Uwzględnienie wielu kryteriów
z wagą 0 i pustych klas zmniejsza bezwzględne wartości wyniku. Niektóre klasy
opisują zbliżone zjawisko, np. drogi i jezdnie albo budynki i teren zabudowany;
zgodnie z poleceniem każda warstwa pozostaje osobnym kryterium.
Sumowanie w komórce nie ocenia ciągłości połączeń ani parametrów konkretnego
pojazdu, stanu podłoża, głębokości wód czy nachylenia z NMT.

## Uruchomienie lokalne i kontrola

Skrypt używa dotychczasowego połączenia z `bdot_common.connect` i wymaga
`TARGET_ENVIRONMENT=env-test`, `PGHOST`, opcjonalnie `PGPORT`,
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`. Uruchomienie z katalogu `app`:

```text
python -m python.calculate_iop --report iop_validation.json
python -m python.validate_iop --output iop_validation.json
```

Opcja `--weights` pozwala wskazać inny plik wag. Ponowne obliczenie odtwarza
wszystkie trzy tabele wynikowe i widoki w jednej transakcji. Przy błędzie dane
nie są publikowane. Nie należy ręcznie edytować tych tabel — zmiany wag
wprowadza się w JSON, po czym ponownie uruchamia skrypt.
Po aktualizacji wcześniejszych agregacji trzeba ponownie obliczyć IOP.

`analysis.iop_normalization` zawiera 219 maksimów i liczby komórek niezerowych.
`analysis.iop_metadata` zapisuje datę obliczenia, liczbę kryteriów, sumę kontrolną
konfiguracji i odcisk danych źródłowych. Walidator wykrywa także nieaktualność
względem wcześniejszych agregacji.

Kontrola obejmuje wszystkie wiersze: zgodność kopii surowych danych i geometrii,
pełne pokrycie 73 klas, kolejność kolumn, maksima 1 dla niepustych kryteriów,
zera przy pustych kryteriach, brak NULL, przedziały i niezależne przeliczenie IOP.
Test na małym zbiorze sprawdza dodatkowo wynik ręczny, dzielenie wartości
całkowitych, pustą warstwę, neutralną wagę i odrzucenie błędnych danych.

```sql
SELECT id,bubd_a,bubd_a_norm,bubd_a_waga,
       skdr_l,skdr_l_norm,skdr_l_waga,iop
FROM analysis.iop_h3_8 ORDER BY id LIMIT 20;

SELECT metric_column,label,weight,rationale
FROM analysis.iop_criteria ORDER BY metric_column;
```

## Wizualizacja IOP w QGIS

Skrypt `app/python/qgis_iop_project.py`, uruchamiany interpreterem
`python-qgis.bat` z instalacji QGIS, tworzy projekt
`IOP_Warszawa_H3_7_8_9` zapisany bezpośrednio w PostgreSQL, w schemacie `qgis`.
Każda warstwa korzysta z dostawcy `postgres` i widoków `viz.iop_h3_7/8/9`
przez połączenie `[PSIP] env-test` (`localhost:5434`, baza `psip`).
Projekt i jego style są w bazie; nie ma zależności od lokalnego GeoPackage
ani projektu `.qgz`. Do uruchomienia skryptu potrzebne jest `PGPASSWORD`.

Skala główna jest identyczna dla H3 7, 8 i 9: **[-1,+1]**, 200 równych
przedziałów o szerokości **0,01**, liniowo rozmieszczone kolory od czerwieni
`#ff0000` do bieli `#ffffff`. Skrajne przedziały mają dokładnie kolory końcowe.
Przy obecnych wartościach bliskich zera kolory skali głównej są podobne.

Dodatkowa, domyślnie wyłączona grupa „szczegóły” ma wspólną skalę
**[-0,07,+0,03]**, 20 równych przedziałów o szerokości **0,005**.
To wyłącznie inny sposób kolorowania tej samej kolumny `iop`; nie zmienia
wartości indeksu i nie stanowi skali [-1,+1]. W tym wariancie czerwony
odpowiada dolnemu końcowi skali szczegółowej, a biały górnemu.

W każdej grupie można przełączać H3 7/8/9, wybierając jedną siatkę naraz.
Projekt ma również sześć motywów mapy: po jednym dla każdej kombinacji
rozdzielczości i skali. Domyślny widok to H3 8 ze skalą główną [-1,+1].
Geometrie analityczne pozostają w EPSG:2180, prezentacja jest w EPSG:3857.

Skrypt sprawdza projekt po ponownym odczytaniu z bazy: źródła PostgreSQL,
poprawność warstw, liczbę klas, równość przedziałów i kolory końcowe.
Opcjonalny `--preview-dir` zapisuje obrazy kontrolne renderowane z bazy;
obrazy nie są źródłem danych dla projektu QGIS.

## Publikacja kodu w QA

Na gałąź `env-qa` trafia kod, konfiguracja wag, testy i dokumentacja.
Zgodnie z decyzją użytkownika ten etap nie kopiuje danych ani wyników IOP
do bazy QA. Dotychczasowy workflow `Start Remote Database` nadal uruchamia
kontener przypisany do gałęzi; nie zasila go wynikami IOP.

Workflow `Verify IOP (QA)` buduje obrazy i wykonuje testy jednostkowe oraz
przypadki kontrolne PostGIS w osobnym, tymczasowym kontenerze z bazą
`iop_ci`. Kontener i sieć są usuwane po teście. Workflow nie korzysta z danych,
wolumenów ani sekretów baz `env-test`, `env-qa` lub `main`.
Wartość `TARGET_ENVIRONMENT=env-test` w teście spełnia istniejące zabezpieczenie
modułu połączenia; host `postgis` wskazuje wyłącznie tymczasową bazę CI.

Ochrona skryptów importu i obliczeń pozostaje ograniczona do `env-test`.
Przeniesienie kodu do `main` jest osobnym etapem wymagającym zatwierdzenia użytkownika.
