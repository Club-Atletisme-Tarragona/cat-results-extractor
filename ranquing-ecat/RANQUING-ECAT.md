# RANQUING ECAT - Regles i Aprenentatges

Document de referència per al processament de les dades del Ranking ECAT (Excel → CSV).

## Estructura del CSV

| Columna | Descripció |
|---------|-----------|
| `prova` | Nom de la prova (idèntic al nom del fitxer, ex: `60_ll_S12`, `4x100_Cadet`, `Alçada`) |
| `marca` | Temps/distància de l'atleta |
| `nom` | Nom complet de l'atleta |
| `any` | Any de naixement |
| `lloc` | Lloc de la prova (ciutat) |
| `data` | Data de la prova en format `YYYY-MM-DD` (o `0000-00-00` si no es coneix) |
| `vent` | Vent en m/s (ex: `+1.2`, `-0.4`) o `null` |
| `manual` | `1` = marca manual (dècimes), `0` = marca electrònica (centècimes) |
| `pc` | `1` = marca PC (Proves de Competició), `0` = altre |

**Nota**: No hi ha columna `gender`. El gènere es dedueix del nom del fitxer:
- `*_femeni`, `*_F`, `*_FEM` → Femení
- `*_masculi`, `*_M` → Masculí
- La resta → no especificar

**Nota**: `prova` és la primera columna i sempre coincideix amb el nom del fitxer.

## Identificació de Marques

### Manual vs Electrònica
- **Manual (manual=1)**: Marques amb **1 decimal** després de convertir a número (ex: 8.0, 8.6, 8.3, 9.1) → cronometratge manual amb dècimes.
- **Electrònic (manual=0)**: Marques amb **2 decimals** després de convertir a número (ex: 8.44, 8.52, 8.89, 10.07) → cronometratge electrònic amb centècimes.
- **Regla**: Compta les dècimes després de convertir el valor a número decimal.
  - 1 decimal → manual=1 (dècimes)
  - 2 decimals → manual=0 (centècimes)
- **Excepció — Salts i Llançaments**: Distàncies i alçades sempre `manual=0`. Format `X.XX` amb 2 decimals (ex: `1.45`, `7.57`, `35.13`). El separador original (`''`, `"`, `,`, `.`) no importa, només el resultat final.

### Valor PC
- **PC (pc=1)**: Vent de la prova és "PC" (Proves de Competició). Indica competició oficial.
- **No PC (pc=0)**: Vent numèric (`1.4`, `-0.9`) o buit. Pot ser entrenament o competició no oficial.
- **Regla**: `pc=1` SIEMPRE quan vent="PC", independentment de `manual`.

## Dates

- Formato d'entrada: variat (`MM/DD/YYYY`, `DD/MM/YYYY`, `YYYY-MM-DD`, `DD-MM-YYYY`, `YYYY/MM/DD`)
- Formato de sortida: `YYYY-MM-DD`
- Si falta la data: `0000-00-00`
- Si falta el lloc: `Unknown`

### Regex de conversió
```
DD/MM/YYYY    → {reverse} DD/MM/YYYY is usually DD/MM/YYYY (day first in European format)
MM/DD/YYYY    → {reverse} MM/DD/YYYY is US format, swap to DD/MM/YYYY then YYYY-MM-DD
YYYY-MM-DD    → Already correct
DD-MM-YYYY    → Swap to YYYY-MM-DD
YYYY/MM/DD    → Replace / with -
```

## Excel Font

### Estructura general
Cada sheet de l'Excel conté dades de **masculí (esquerra)** i **femení (dreta)** separades per una columna buida.

### Problemes detectats
1. **Columnes de vent**: En molts sheets, la columna de vent està entre `marca` i `nom` (no al final). L'script original no la detecta.
2. **Files de posició**: Molts sheets inclouen file de posició (1.0, 2.0, 3.0...) a la primera columna que cal ignorar.
3. **Capçaleres inconsistents**: Alguns sheets tenen capçaleres `None` (ex: `300 ll S16`, `Alçada S16`). La detecció automàtica falla.
4. **Formats de marca variats**: `7'30"`, `7"37`, `7.7`, `8''2`, `3'53"86` — cal normalitzar a decimals.
5. **Marcas amb 'm'**: Ex: `8.09 m` → cal treure el 'm' de la marca.
6. **PC com a marca**: En salts, "PC" apareix a la columna de vent o marca.

### Estructura per tipus de sheet

#### Track (60ll, 100ll, 200ll, etc.)
```
Col 0: Posició (ignorar)
Col 1: Marca (temps)
Col 2: Nom
Col 3: Any
Col 4: Lloc
Col 5: Data
Col 6: Vent (o "PC")
```

#### Salt (Llargada, Triple, Alçada, Perxa)
```
Col 0: Marca (distància/alçada)
Col 1: Vent (opcional, pot ser =1, PC, numèric)
Col 2: Nom
Col 3: Any
Col 4: Lloc
Col 5: Data
Col 6: Categoria
```

#### Field (Pes, Disc, Martell, Javelina)
```
Col 0: Marca
Col 1: Nom
Col 2: Any
Col 3: Lloc
Col 4: Data
Col 5: Categoria
```

## Neteja de Marques

### Formats de temps detectats
| Format original | Convertit | Descripció |
|----------------|-----------|------------|
| `7'30"` | 7.30 | Manual, centècimes |
| `7"37` | 7.37 | Manual, centècimes |
| `8''0` | 8.0 | Manual, 1 decimal |
| `8''44` | 8.44 | Electrònic, 2 decimals |
| `9"52` | 9.52 | Electrònic, 2 decimals |
| `9"2` | 9.2 | Manual, 1 decimal |
| `7.7` | 7.7 | Electrònica |
| `8.09 m` | 8.09 | Distància amb unidad |
| `3'53"86` | 3:53.86 | Longa distància (min:sec.cent) |

### Regex de neteja
```python
# Centècimes manual: X'YY"ZZ → X:YY.ZZ (longa distància)
r"(\d{1,2})'(\d{2})\"(\d{2})"

# Formata manual curt: X'XX" o X"XX → X.XX
r"['\"″]" → .

# Treure 'm' final de distància
r"\s*m$" → ""

# Normalitzar separador decimal: , → .
r"," → "."
```

## Aprenentatges Clau

1. **Sempre validar l'Excel font**: L'script `extract_sheets.py` pot fallar en sheets amb capçaleres `None`.
2. **Les dates estan en formats variats**: L'Excel pot tenir dates com a `datetime` objects o strings amb formats diferents.
3. **Manual = 1 decimal vs 2 decimals**: Marques amb 1 decimal → `manual=1` (dècimes). Marques amb 2 decimals → `manual=0` (centècimes). PC es determina pel vent ("PC" → `pc=1`).
4. **Nom trencat per coma**: Quan el nom conté una coma (ex: `"ESCRIBANO GOMEZ, JOSEP LLUIS"`), reconstruir com `JOSEP LLUIS ESCRIBANO GOMEZ` (última part + primera part).
5. **Marques amb `-`**: Marques com `9.6-`, `10.3-` → el `-` final s'ha d'ignorar, la marca és `9.6`, `10.3` (1 decimal → manual=1).
6. **Marques amb `'`**: `9'51` → 9.51 (2 decimals → manual=0), diferent de `9''51` que seria 9.51 també.
7. **Marques amb `0X"X`**: `09"7` → 9.7 (1 decimal → manual=1). El `0` inicial s'ha d'ignorar.
8. **Marcas amb `"0`**: `11"0`, `10''0`, `10"2` → 11.0, 10.0, 10.2 (1 decimal → manual=1).
9. **Format de temps per distància**: A partir de 300m, les marques han de tenir format `MM:SS.cc` (minuts:segons.centècimes). Ex: `38.02` → `00:38.02`, `01:20.20` → `01:20.20`.
10. **Vent amb `,`**: El vent pot venir amb coma `1,8` → convertir a punt `1.8`.
4. **Files de posició enganyoses**: Les files com ara `(1.0, "7''30", 'JAVIER...')` tenen posició a col 0 que cal ignorar.
5. **Columna de vent desplaçada**: En track, el vent està a la col següent de marca, no al final.

## Relleus (4x60, 4x100, etc.)

- Cada atleta del relleu és una fila independent amb la **mateixa marca, lloc i data**.
- La columna `nom` conté **només el nom de l'atleta**, no l'equip sencer.
- Si les dades originals tenen l'equip sencer al camp `nom` (separat per `-` o línies múltiples), **separar cada atleta en una fila individual**.
- Exemple: `PAU CRESPO-ERIC DE LA ROSA-GUILLEM FERRAN-VICTOR JIMENEZ` → 4 files amb `prova="4x60"`, mateixa `marca`, `lloc`, `data`.
- **No hi ha columna `any` individual** per a relleus — si no es pot assignar, deixar buit.
- Totes les marques de relleus són electròniques → `manual=0`.
