# UDIM Tiler

Deler et bilde i UDIM-tiles og eksporterer dem som PNG, EXR eller JPG, i én eller flere oppløsninger.

## Installere

Last ned **UDIM-Tiler-Setup.exe** fra [siste release](https://github.com/highresno/udim/releases/latest) og kjør den. Appen installeres for din bruker, så det trengs ikke administrator.

Installeren er ikke signert, så Windows SmartScreen kan si «Windows beskyttet PC-en». Velg *Mer informasjon* og *Kjør likevel*.

## Oppdatere

Knappen øverst til høyre i appen sjekker om `main` på GitHub har nye commits. Når GitHub Actions har bygget en installer for den nyeste commiten, kan du trykke **Oppdater nå**. Appen laster ned installeren, installerer stille og starter på nytt. Appen sjekker også automatisk ved oppstart.

Hver push til `main` bygger en ny installer (tar ca. 5–10 minutter) og publiserer den som en release.

## Funksjoner

- Åpne eller dra inn PNG, JPG, TIFF, EXR, TGA, PSD, HDR m.fl.
- UDIM-nummerering 1001 nede til venstre, 10 per rad (maks 10 i X).
- Flere bilder i faner, og prosjekter lagres som `.udimt` (dobbeltklikk åpner dem i appen).
- Listen til venstre viser mapper og filer med anslått filstørrelse per tile, og faktisk størrelse etter eksport.
- Ujevn deling: fyll ut, beskjær eller strekk.
- Oppløsninger 1:1, 1/2, 1/4, 1/8, gjerne flere samtidig. Hele bildet skaleres før deling, så det blir ingen skjøter.
- PNG: BW/RGB/RGBA, 8/16 bit, komprimering. EXR: BW/RGB/RGBA, half/float, 10 codecs med nivå for zip/dwa. JPG: BW/RGB, kvalitet.
- Mappe: `Navn_PNG_BW_16bit_50%_2048_2048` (størrelse per tile). Filer: `Navn_2048x2048.1001.png` som standard (Blender-kompatibelt) eller `Navn_2048x2048_1001.png`.
- Fargerom: EXR lagres lineært, PNG/JPG som sRGB.

## Utvikling

```bash
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app/main.py             # åpner appen
python app/main.py --selftest  # eksporterer testbilder i alle formater
```

`app/ui/index.html` kan også åpnes direkte i en nettleser. Da er eksporten simulert.

| Fil | Innhold |
|---|---|
| `app/main.py` | Starter vinduet (pywebview, bruker Edge WebView2) |
| `app/api.py` | Funksjonene brukergrensesnittet kaller |
| `app/udim_core.py` | Oppdeling, skalering og eksport (OpenImageIO + numpy) |
| `app/updater.py` | Sjekker GitHub og installerer nye versjoner |
| `app/ui/index.html` | Brukergrensesnittet |
| `build/installer.iss` | Inno Setup-skript for installeren |
| `.github/workflows/release.yml` | Bygger og publiserer installeren |
