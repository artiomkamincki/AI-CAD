# PDF → Specyfikacja wentylacji

Serwis FastAPI, który przetwarza PDF-y z rysunkami wentylacji i generuje arkusz Excel ze specyfikacją elementów oraz przekrojów kanałów (bez długości).

## Wymagania i instalacja

```bash
pip install -r requirements.txt
```

## Uruchomienie

```bash
uvicorn app.main:app --reload --port 8000
```

## Użycie

Żądanie HTTP z wysłaniem pliku PDF:

```bash
curl -F "file=@sample.pdf" http://localhost:8000/extract
```

Wyniki (plik `spec.xlsx`) znajdziesz w katalogu `results/<job_id>/spec.xlsx`.

## Uwagi

- W specyfikacji nie są liczone długości kanałów – tylko liczba metek/wystąpień.
- Dokładność rozpoznania zależy od jakości PDF-u oraz efektów OCR.
- Elementy armatury wymagają podpisów z rozmiarami w pobliżu symboli.
