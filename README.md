# Cat Results Extractor

Eina per extreure els resultats d'atletisme dels atletes del **Club Atletisme Tarragona (CATT)** des de PDFs de resultats de competicions.

## Descripció

L'eina llegeix un PDF de resultats d'una competició d'atletisme, identifica les proves on participen atletes del CATT i n'extreu les dades (nom, lloc, marca, disciplina, etc.) generant un fitxer JSON amb els resultats.

### Proves suportades

- **Track** (pista): sprints, mig fons, fons, vallas
- **Marcha**: marxa atlètica
- **Jumps** (salt): Llargada, Triple Salt
- **Height** (altura): Altura, Pertiga
- **Field** (campo): Disco, Martillo, Peso, Jabalina
- **Relay** (relleus): 4x100m, 4x400m

Cada tipus de prova té el seu propi mètode d'extracció ja que els PDFs de resultats utilitzen formats diferents.

## Requirements

- **Python 3.8+**
- **poppler-utils** (comanda `pdftotext`)

### Instal·lació de dependències

```bash
# Ubuntu / Debian
sudo apt install poppler-utils

# macOS
brew install poppler

# Arch Linux
sudo pacman -S poppler
```

No cal cap llibreria de Python addicional, tot fa servir el mòdul estàndard.

## Ús

```bash
python3 extract_catt.py <fitxer.pdf>
```

### Exemple

```bash
python3 extract_catt.py resultat-20260314-catuniversitari.pdf
```

### Sortida

L'eina genera un fitxer JSON amb el mateix nom que el PDF (substituint `.pdf` per `.json`):

```bash
resultat-20260314-catuniversitari.json
```

El JSON inclou:

- **event_name**: Nom de la competició
- **event_date**: Data de la competició
- **event_location**: Localitat
- **results**: Llista de resultats amb:
  - `athlete_name`: Nom de l'atleta
  - `athlete_dob`: Data de naixement
  - `athlete_id`: Número de llicència
  - `performance`: Marca obtinguda
  - `discipline`: Prova/disciplina
  - `wind`: Vent (en proves de pista)

## Estructura del codi

- `extract_text()`: Converteix el PDF a text amb `pdftotext -layout`
- `parse_header()`: Extreu el nom de la competició, ubicació, localitat i data
- `classify_event()`: Classifica cada prova (track, jump, height, field, relay, marcha)
- `find_section_boundaries()`: Detecta les seccions de cada prova al PDF
- `find_catt_athletes_in_section()`: Troba els atletes del CATT dins cada prova
- `parse_catt_athlete()`: Extrau les dades de cada atleta
- `parse_relay_section()`: Gestiona les proves de relleus (un registre per membre)
- `deduplicate_results()`: Elimina duplicats (sèries, finals, etc.)

## Format de sortida JSON

```json
{
  "event_name": "Jornada 8 Campionat de Catalunya...",
  "event_date": "14/03/2026",
  "event_location": "Tarragona",
  "total_results": 15,
  "results": [
    {
      "athlete_name": "NOM ATLETA",
      "athlete_dob": "01/01/2000",
      "athlete_id": "CL12345",
      "performance": "11.45",
      "discipline": "100m Hombres",
      "wind": "-0.5"
    }
  ]
}
```

## Integració amb la web del CATT

El JSON generat es pot utilitzar per importar les marques directament a l'importador de marques de la web del Club Atletisme Tarragona.

## Workflow de processament

El procés de processament de resultats segueix aquests passos:

1. **Extracció**: Executar `python3 extract_catt.py <fitxer.pdf>` per generar el JSON a `json/`
2. **Verificació**: Revisar el fitxer `status.html` per veure l'estat de tots els resultats
3. **Importació**: Un cop importats al sistema del CATT, moure el JSON a `json/imported/`
4. **Actualització**: Actualitzar `status.html` — canviar la ruta a `json/imported/`, marcar com `✅ Si` i assignar la persona que ho ha fet

L'status.html és el punt de referència visual per saber:
- Quins fitxers s'han processat i quins encara són pendents
- Qui ha processat cada fitxer (Dídac, Peio, etc.)
- Quins ja s'han importat al sistema (estàn a `json/imported/`)

## .gitignore

Els fitxers `.pdf` originals es ignoren per Git. Els fitxers `.json` a `json/` i `json/imported/` **sí que es versionen** perquè són la sortida del procés d'extracció i necessiten ser accessibles per a importació.
