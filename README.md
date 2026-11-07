# KM Sammanställning

Statisk webbplats som visar resultat från klubbmästerskap (KM). Besökare kan filtrera och ladda ner PDF. Bara ägaren av repot kan lägga till resultat.

## Personuppgifter

Råa Lenex-filer innehåller mer än sidan visar (licensnummer, fullständiga födelsedatum, mellantider, barn under 13 m.m.). **De publiceras aldrig.** I stället skapar `lenex_extract.py` en slimmad datafil i mappen `data/` med bara det som visas: namn, födelseår, kön, klubb, gren, tid, poäng och åldersklass. Endast `index.html` och `data/` publiceras. Sidan är markerad `noindex` så att sökmotorer inte ska indexera den.

Hela mappen `results/` är undantagen via `.gitignore`, så ingenting du lägger där följer med till GitHub. Mappen skapas av skriptet om den saknas. Checka aldrig in dem, eftersom git sparar historik och det som en gång laddats upp inte går att dra tillbaka på ett enkelt sätt.

## Lägga till resultat (bara ägaren)

1. Lägg Lenex-filen (`.lxf` eller `.lef`) i mappen `results/` på din dator.
2. Kör `python lenex_extract.py`. Det skapar `data/<KM>.json` och uppdaterar `data/index.json`. Reglerna i skriptet (minst fem startande per gren, 12 år och yngre och utom tävlan tas bort) tillämpas innan datan publiceras.
3. Kontrollera sidan lokalt (se nedan).
4. Committa `data/` och pusha till `main`. GitHub Actions publicerar om sidan.

Ta bort ett KM genom att ta bort dess fil i `data/`, köra skriptet igen så att `index.json` uppdateras, och pusha.

## Publicera första gången

1. Skapa ett publikt repo på GitHub och pusha innehållet här (grenen ska heta `main`). Kontrollera med `git status` att inga filer i `results/` är med.
2. Under *Settings → Pages*, välj *Build and deployment → Source: GitHub Actions*.
3. Skydda gärna `main` under *Settings → Branches*. Andra kan inte ändra repot om de inte får skrivrättigheter.

## Köra lokalt

    python serve.py

Öppna http://localhost:8000.
