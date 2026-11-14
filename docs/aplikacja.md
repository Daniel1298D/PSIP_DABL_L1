# GeoAnaliza — aplikacja okienkowa

Własna aplikacja w Pythonie ma oddzielne okno i uruchamia się plikiem
`GeoAnaliza.cmd`. Nie uruchamia interfejsu QGIS. Do rysowania mapy używa
zainstalowanych bibliotek GIS i Qt z instalacji QGIS 3.44.1.

## Uruchomienie

1. Uruchom Docker Desktop.
2. Upewnij się, że działa kontener `remote-db-env-test-postgis-1`.
3. Otwórz `GeoAnaliza.cmd` z głównego katalogu projektu lub skrót **GeoAnaliza**
   na pulpicie.

Pliki źródłowe są w tym samym projekcie PyCharm:

- `app/desktop_main.py` — uruchamianie aplikacji i kontrola połączenia.
- `app/desktop/window.py` — własny interfejs, mapa i obsługa przycisków.
- `app/desktop/theme.py` — kompletne palety jasna/ciemna i style kontrolek.
- `app/desktop/data.py` — bezpośredni odczyt warstw z PostgreSQL.
- `app/python/iop_style.py` — wspólna skala IOP aplikacji i generatora projektu QGIS.

Przy uruchomieniu z terminala PyCharm można użyć:

```powershell
& 'C:/Program Files/QGIS 3.44.1/bin/python-qgis.bat' app/desktop_main.py
```

Launcher `GeoAnaliza.cmd` konfiguruje potrzebne ścieżki bibliotek tylko we
własnym procesie. Nie zmienia systemowej konfiguracji Pythona. Inny katalog
instalacji można wskazać zmienną `PSIP_QGIS_ROOT`.

## Dane

Źródłem są widoki `viz.iop_h3_7`, `viz.iop_h3_8`, `viz.iop_h3_9` oraz granica
`grid.powiat` w istniejącej bazie `psip`, domyślnie `localhost:5434` (env-test).
Aplikacja nie otwiera plików z kopią tych danych ani nie wymaga zapisanego
projektu QGIS. Każdy odczyt pochodzi bezpośrednio z dostawcy PostgreSQL.
Nie modyfikuje tabel, wag ani wartości IOP w bazie.

Domyślna konfiguracja połączenia jest odczytywana z lokalnego profilu QGIS
`[PSIP] env-test`. Można ją zastąpić zmiennymi procesu:

| Zmienna | Znaczenie |
|---|---|
| `PSIP_DB_HOST` | adres serwera |
| `PSIP_DB_PORT` | port, domyślnie 5434 |
| `PSIP_DB_DATABASE` | nazwa bazy |
| `PSIP_DB_USERNAME` | użytkownik PostgreSQL |
| `PSIP_DB_PASSWORD` | hasło, alternatywnie `PGPASSWORD` |

Hasło nie jest zapisane w kodzie ani pokazywane w interfejsie. Brak połączenia
daje komunikat w aplikacji i przycisk ponownego odczytu. Przycisk odświeżania
w prawym górnym rogu mapy ponownie pobiera dane z bazy.

## Mapa i narzędzia

Przy pierwszym uruchomieniu utwórz lokalne konto GeoAnalizy. Nazwa użytkownika
ma od 3 do 64 znaków, a hasło co najmniej 8. Kolejne uruchomienia wymagają
logowania. Przycisk **Wyloguj się** kończy sesję i wraca do formularza.
Konto jest przypisane do profilu Windows. Aplikacja zapisuje pochodną hasła
obliczoną przez `scrypt` z losową solą w `%LOCALAPPDATA%/GeoAnaliza/account.sqlite3`.
Dane tego konta służą tylko do logowania w GeoAnalizie.

- **Wagi IOP** — wybierz jedną z 73 warstw i ustaw jej wagę suwakiem od −1 do +1.
  Mapa przelicza IOP według dotychczasowego wzoru, z dzielnikiem równym liczbie
  kryteriów. Wagi można przywrócić pojedynczo lub wszystkie naraz. Przeliczenie
  dotyczy sesji aplikacji i korzysta z normalizacji z PostgreSQL.
- **Edytuj styl** — ustaw ujemne minimum i dodatnie maksimum skali kolorów.
  Biel oznacza IOP równy 0, także w skali niesymetrycznej. Wartości poza
  ustawionym zakresem otrzymują skrajne kolory. Wybór skali w panelu pozwala
  wrócić do widoku pełnego albo szczegółowego.
- **Szukaj atrybutów** — wybierz kolumnę aktywnej siatki, wpisz całość lub
  fragment wartości, a następnie wskaż wynik i kliknij **Pokaż na mapie**.
  Wybór `IOP z aktualnymi wagami` obejmuje wartość po zmianach suwaków.
  W zakładce **Warstwy** wyszukiwanie dotyczy zaznaczonej warstwy.

### Warstwy, współrzędne i pomiar

6. Zakładka **Warstwy** pokazuje kolejność rysowania. Warstwa wyżej na liście
   znajduje się na wierzchu mapy. Użyj przycisków **Wyżej**, **Niżej**
   i pól wyboru widoczności.
7. Stopka pokazuje szerokość i długość kursora w stopniach **EPSG:4326**.
8. **Wczytaj SHP** otwiera wybór plików lub folderu. Wybór folderu wczytuje
   pliki `.shp` z wybranego katalogu. Pliki składowe, w tym `.prj`, powinny
   znajdować się obok `.shp`. Wczytane warstwy pojawiają się na wierzchu.
9. Kliknij **Zmierz odległość**, a potem wskaż dwa miejsca na mapie. Wynik
   w metrach pojawi się w pasku **Odległość** nad mapą. Pomiar odbywa się
   po elipsoidzie WGS84. Następne kliknięcie rozpoczyna nowy pomiar. **Esc**
   przywraca przesuwanie mapy i zachowuje ostatni wynik. Przycisk **Wyczyść
   pomiar** usuwa wynik i odcinek.
10. **Nowa warstwa punktowa** tworzy nazwaną warstwę EPSG:4326 i włącza
    dodawanie punktów. Każde kliknięcie na mapie dodaje jeden punkt. Aby
    wznowić dodawanie, wybierz warstwę i kliknij **Dodawaj punkty na mapie**.
    Punkty i lista warstw użytkownika są przechowywane w bieżącej sesji.

- Interaktywna mapa: przesuwanie myszą, powiększanie kółkiem i przyciskami,
  powrót do zasięgu Warszawy.
- Wybór H3 7, H3 8 lub H3 9; liczby komórek i zakres IOP pochodzą z bazy.
- Dotychczasowe skale IOP: pełna [-1,+1] i szczegółowa [-0,07,+0,07].
  Wartości ujemne są czerwone, zero białe, a dodatnie zielone.
- Legenda, opcjonalny obrys Warszawy, współrzędne kursora WGS84 i skala mapy.
- Przycisk **Tryb ciemny / Tryb jasny** w prawym górnym rogu.
  Zmienia nagłówek, panel warstw, kontrolki, legendę, tło mapy, stopkę
  i na wspieranych wersjach Windows także pasek tytułu.
- Skrót klawiaturowy motywu: **Ctrl+Shift+L**.
- Zapamiętanie motywu i wybranej siatki po ponownym uruchomieniu.

Barwy samych danych IOP zachowują swoje znaczenie w obu motywach; białe
heksagony nadal oznaczają wartości bliskie zeru, również w ciemnym interfejsie.
Preferencje wyglądu zapisuje `QSettings` wyłącznie w ustawieniach własnej
aplikacji `PSIP/GeoAnaliza`.

### Podgląd obiektu i eksport

11. Kliknij obiekt na mapie. Zakładka **Obiekt** pokazuje jego atrybuty.
    Dla H3 zobaczysz identyfikator, aktualny IOP i niezerowe powierzchnie,
    długości oraz liczby punktów z BDOT10k. Gdy widoczne obiekty się pokrywają,
    wybierana jest najwyższa z trafionych warstw. Obrys Warszawy pozostaje obrysem mapy.
12. **Przybliż do obiektu** dopasowuje zasięg mapy do wybranego obiektu.
13. **Tryb jasny / Tryb ciemny** działa również w zakładce **Obiekt** i w oknach narzędzi.
14. **Eksport PDF** zapisuje bieżący widok widocznych warstw na stronie A4
    w orientacji poziomej. PDF zawiera skalę wydruku i skalę barw IOP,
    jeśli siatka H3 jest widoczna.

## Kontrola

```powershell
& 'C:/Program Files/QGIS 3.44.1/bin/python-qgis.bat' app/desktop_main.py --validate
```

Kontrola odczytuje wszystkie trzy warstwy, ich liczby komórek i zakresy IOP,
sprawdza źródło PostgreSQL, układ EPSG:3857, obie skale kolorów i obie palety.
Nie uruchamia okna ani nie modyfikuje bazy. Błędy uruchomienia programu
okienkowego są zapisywane lokalnie w `%LOCALAPPDATA%/GeoAnaliza/startup.log`.
