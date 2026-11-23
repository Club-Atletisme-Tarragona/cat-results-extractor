# Backfill empty event_name from the sheet header (issue #23)

Authorized: user said "si" to continuing with #23 after #32 closed.
Parent: GitHub issue #23 — 210 files (5,998 result rows) carry an empty
`event_name`, spread across every season 2005–2026.

## Why now

`parse_header` was repaired in #32 (`a5e65b07`) to read the real meeting header
instead of the first date-looking line. That fix is what makes this backfill
tractable: the same header text that supplies the date also supplies the
competition name. Every affected file carries `event_src`, so no re-scraping is
needed.

## Specs

S1. `event_name` is the sheet's own header text, **verbatim** (AGENTS.md): do not
    normalise, translate, title-case or append the venue. It is venue evidence
    for location normalisation, so altering it destroys provenance.
S2. A name is only written when it comes from the PDF **header block** — the same
    block #32 defined. Never derive it from the filename, the URL, or the
    directory.
S3. Reject as name candidates the lines that are not the competition title:
    stamps (weekday), `RCAT`/`RCAM`/`Rècord`, season-best/`MMP`, DOB context,
    result-table headers, and bare venue/date lines.
S4. Files whose header yields nothing usable keep the empty field and are
    reported as a worklist with the raw first lines, so the next layout family
    can be added deliberately. Never invent a name to reduce the count.
S5. Every written name records its evidence: the header lines read from the PDF.
S6. Verification: suite green; `scripts/check_plausibility.py` must not exceed
    **259**; the empty count must drop by exactly the number of files written;
    `scripts/check_event_dates.py` must stay at **0 open**; a differential check
    because `parse_header` is shared.

## Tasks

| ID | Specs | Route | Commit | Status |
|----|-------|-------|--------|--------|
| T1 | S1,S2,S3 | Header-name extraction: reject non-title lines, return the verbatim title | `extract_catt.py`, `tests/test_parse_header_names.py` | done |
| T2 | S2,S5 | Dry-run pass over all 210: how many resolve, with per-file evidence | — | done (204/210) |
| T3 | S1,S2,S5 | Apply the resolvable names (sibling temp + `os.replace`, `event_name` only) | 204 `seasons/*/json/*.json` | done |
| T4 | S4 | Emit the unresolvable worklist with raw header lines, grouped by layout | `reports/event_name_backfill_unresolved.csv` | done (6 rows) |
| T5 | S6 | Verification + work-unit commit | — | done (verification; commit by parent) |

## Log

L1. si (continue with #23 after #32)
L2. T1 red: `tests/test_parse_header_names.py` written first, 14 of 20 tests
    failing on the base commit (`ACTA DEL CAMPEONATO` returned for the 2017
    GP Marxa Sant Cugat sheet, `''` for Campmany 2007 and Trofeu Nadal 2024,
    `4a. Jornada` for the 2005 llançaments sheet).
L3. T1 green: `parse_header` now reads the title from `_header_block()` only,
    filters every candidate through `_is_title_candidate()` (labels, layout
    markers, venue/club lines, date lines, discipline headers, session/round
    labels, category labels, merged two-column lines) and falls back to the
    first plausible title line. The keyword tiers stay in front of that fallback
    because they disambiguate sheets that print a round label above the title
    ("JORNADA PRÈVIA" / "CAMPIONAT DE CATALUNYA …"). No date logic changed.
L4. T2 dry run over the 210: 204 resolve, 6 do not.

    | family | files | resolved | example header line |
    |--------|-------|----------|---------------------|
    | title on the first non-empty line | 186 | 186 | `CRITERIUM CAMPMANY (2a. Jornada)` |
    | title after a layout marker (`GENERAL!A1`) | 9 | 9 | `GENERAL!A1` |
    | title after a round number line | 9 | 9 | `4a. Jornada` |
    | no title line in the header | 6 | 0 | `CONTROL            22-1-2011` |

    Per season (resolved/total): 2005 11/11, 2006 8/8, 2007 9/9, 2008 3/3,
    2009 6/6, 2010 13/13, 2011 14/16, 2012 15/15, 2013 23/23, 2014 8/10,
    2015 11/12, 2016 23/24, 2017 6/6, 2018 6/6, 2019 10/10, 2020 1/1,
    2021 10/10, 2022 4/4, 2023 3/3, 2024 9/9, 2025 8/8, 2026 3/3.
L5. T3 applied: 204 files, sibling temp + `os.replace`, round-trip guarded (a
    file whose dump would not reproduce the stored bytes is refused rather than
    reformatted). `git diff -U0 -- seasons/` is 204 `"event_name"` removals and
    204 additions, nothing else. Empty `event_name`: 210 → 6.
L6. T4 worklist: `reports/event_name_backfill_unresolved.csv`, 6 rows in five
    families — `club line only` (1), `no title line (sheet opens on a
    discipline)` (2), `title+date on one line` (1), `title+venue+date on one
    line` (1), `two-column header (title and venue merged)` (1). Each row keeps
    the raw header lines so the next family is a deliberate decision.
L7. T5 verification: suite 188 → 208 tests OK; `scripts/check_plausibility.py`
    259 before and after (cap 259); `scripts/check_event_dates.py` 0 open;
    differential check on the five pinned fixture PDFs against the base commit
    in a `mktemp -d`: byte-identical JSON.

## Applied names (evidence: the header line read from the PDF at `event_src`)

Verbatim, one row per file. The diff is the authoritative record; this table is
the human-readable index of which header line each file now carries. Rows are
`file | season | event_name`.

| file | season | event_name |
|------|--------|------------|

| `resul-lligacat-tarragona15510` | 2010 | LLIGA CATALANA DE PROMOCIÓ |
| `resulcambrils16110` | 2010 | TERRITORIAL INFANTIL D'HIVERN 09-10 |
| `resulcambrils230613` | 2013 | TROBADA ANDORRA - CAT MERIDIONAL |
| `resulcampmany10609` | 2009 | Criterium Josep Campmany |
| `resulcampmany13607` | 2007 | Criterium Josep Campmany |
| `resulcampmany20607` | 2007 | CRITERIUM JOSEP CAMPMANY (2a. Jornada) |
| `resulcampmany27607` | 2007 | Criterium Josep Campmany (3a. Jornada) |
| `resulcampmany4707` | 2007 | Criterium Josep Campmany (4a. Jornada) |
| `resulcatabsolutpc30213` | 2013 | 37è CAMPIONAT DE CATALUNYA ABSOLUT EN PISTA COBERTA |
| `resulcatalevi11611` | 2011 | CNAT CATALUNYA ALEVÍ |
| `resulcatalevi90612` | 2012 | CAMPIONAT DE CATALUNYA ALEVÍ |
| `resulcataleviprevia80613` | 2013 | Fase Prèvia Cnat. Catalunya Aleví |
| `resulcatbenjami11611` | 2011 | CNAT CATALUNYA BENJAMÍ |
| `resulcatbenjami90612` | 2012 | CAMPIONAT CATALUNYA BENJAMÍ |
| `resulcatbenjamiprevia90613` | 2013 | Fase Prèvia Cnat. Catalunya Benjamí |
| `resulcatcadet170612` | 2012 | CAMPIONAT DE CATALUNYA CADET |
| `resulcatcadet18611` | 2011 | CNAT. CATALUNYA CADET |
| `resulcatcadet19610` | 2010 | CAMPIONAT CATALUNYA CADET |
| `resulcatcadetpc30313` | 2013 | CAMPIONAT DE CATALUNYA CADET EN PISTA COBERTA |
| `resulcatcadetpc5211` | 2011 | CAMPIONAT CATALUNYA CADET PC |
| `resulcatcadetprevia260512` | 2012 | JORNADA PRÈVIA CAMPIONAT DE CATALUNYA CADET |
| `resulcatcadetprevia90613` | 2013 | Fase Prèvia Cnat. Catalunya Cadet |
| `resulcatclubsalevi130512` | 2012 | CAMPIONAT DE CATALUNYA DE CLUBS ALEVÍ A L'AIRE LLIURE |
| `resulcatclubsalevial20416` | 2016 | CAMPIONAT DE CATALUNYA DE CLUBS - ALEVÍ MASCULÍ |
| `resulcatclubsbenjami130512` | 2012 | CAMPIONAT DE CATALUNYA DE CLUBS BENJAMÍ A L'AIRE LLIURE |
| `resulcatclubsbenjami7511` | 2011 | CNAT CAT CLUBS BENJAMÍ MASCULÍ |
| `resulcatclubsbenjamial30416` | 2016 | Camponat Catalunya Clubs Benjamí Masculí |
| `resulcatclubscadetal30416` | 2016 | CAMPIONAT DE CATALUNYA DE CLUBS - CADET MASCULÍ |
| `resulcatclubsinfantil120512` | 2012 | CAMPIONAT DE CATALUNYA DE CLUBS INFANTIL A L'AIRE LLIURE |
| `resulcatclubsinfantilal20416` | 2016 | CAMPIONAT DE CATALUNYA DE CLUBS - INFANTIL MASCULÍ |
| `resulcatclubsveteranspc12211` | 2011 | CNAT CAT CLUBS VETERANS PC |
| `resulcatcombinadespromocio25260513` | 2013 | CAMPIONAT DE CATALUNYA DE PROVES COMBINADES |
| `resulcatinfantil11611` | 2011 | CNAT CATALUNYA INFANTIL |
| `resulcatinfantil90612` | 2012 | CAMPIONAT DE CATALUNYA INFANTIL |
| `resulcatinfantilpc100312` | 2012 | CAMPIONAT DE CATALUNYA INFANTIL EN PISTA COBERTA |
| `resulcatinfantilpc90313` | 2013 | CAMPIONAT DE CATALUNYA INFANTIL EN PISTA COBERTA |
| `resulcatinfantilpcprevia110212` | 2012 | CAMPIONAT DE CATALUNYA INFANTIL EN PISTA COBERTA |
| `resulcatinfantilpcprevia20313` | 2013 | JORNADA PRÈVIA CAMPIONAT DE CATALUNYA INFANTIL |
| `resulcatinfantilprevia80613` | 2013 | Fase Prèvia Cnat. Catalunya Infantil |
| `resulcatjuniorpc100313` | 2013 | CAMPIONAT DE CATALUNYA JUNIOR EN PISTA COBERTA (- 3.000 m.ll.) |
| `resulcatllancaments170213` | 2013 | CAMPIONAT DE CATALUNYA DE LLANÇAMENTS D´HIVERN |
| `resulcatpromesapc270113` | 2013 | CAMPIONAT DE CATALUNYA PROMESA EN PISTA COBERTA (-3.000 m.ll.) |
| `resulcatveterans120616` | 2016 | CAMPIONAT DE CATALUNYA DE VETERANS INDIVIDUAL i RELLEUS |
| `resulcatveterans220613` | 2013 | CAMPIONAT DE CATALUNYA DE VETERANS |
| `resulcatveteranspc240213` | 2013 | CAMPIONAT DE CATALUNYA DE VETERANS EN PISTA COBERTA |
| `resulccampmany14606` | 2006 | CRITERIUM CAMPMANY (1a. Jornada) |
| `resulccampmany15605` | 2005 | CRITERIUM CAMPMANY (2a. Jornada) |
| `resulccampmany15611` | 2011 | Criterium Josep Campmany |
| `resulccampmany1611` | 2011 | Criterium Josep Campmany |
| `resulccampmany16610` | 2010 | Criterium Josep Campmany |
| `resulccampmany21606` | 2006 | CRITERIUM CAMPMANY (2a. Jornada) |
| `resulccampmany22605` | 2005 | CRITERIUM CAMPMANY (3a. Jornada) |
| `resulccampmany2610` | 2010 | Criterium Josep Campmany |
| `resulccampmany28606` | 2006 | CRITERIUM CAMPMANY (3a. Jornada) |
| `resulccampmany29611` | 2011 | Criterium Josep Campmany |
| `resulccampmany30610` | 2010 | Criterium Josep Campmany |
| `resulccampmany5706` | 2006 | CRITERIUM CAMPMANY (4a. Jornada) |
| `resulccampmany6705` | 2005 | CRITERIUM CAMPMANY (4a. Jornada) |
| `resulccampmany8605` | 2005 | CRITERIUM CAMPMANY (1a. Jornada) |
| `resulccombinades12605` | 2005 | CONTROL DE PROVES COMBINADES |
| `resulcjjp11605` | 2005 | CONTROL JUVENIL-JUNIOR-PROMESA (3a. Jornada) |
| `resulcjjp21505` | 2005 | CONTROL JUVENIL-JUNIOR-PROMESA (2a. Jornada) |
| `resulcjjp7505` | 2005 | CONTROL JUVENIL-JUNIOR-PROMESA (1a. Jornada) |
| `resulcllancaments11207` | 2007 | CRITERIUM DE LLANÇAMENTS D'HIVERN |
| `resulcllancaments1209` | 2009 | CRITERIUM DE LLANÇAMENTS D'HIVERN |
| `resulcllancaments13205` | 2005 | CRITERIUM DE LLANÇAMENTS D'HIVERN |
| `resulcllancaments14210` | 2010 | CRITERIUM DE LLANÇAMENTS D'HIVERN |
| `resulcllancaments23105` | 2005 | CRITERIUM DE LLANÇAMENTS D'HIVERN |
| `resulcllancaments26206` | 2006 | CRITERIUM DE LLANÇAMENTS D'HIVERN |
| `resulcllancaments28107` | 2007 | CRITERIUM DE LLANÇAMENTS D'HIVERN |
| `resulcllancaments29105` | 2005 | CRITERIUM DE LLANÇAMENTS D'HIVERN |
| `resulcllancaments31110` | 2010 | CRITERIUM DE LLANÇAMENTS D'HIVERN (2a Jornada) |
| `resulcllancaments5306` | 2006 | CRITERIUM DE LLANÇAMENTS D'HIVERN |
| `resulcllancaments7210` | 2010 | CRITERIUM DE LLANÇAMENTS D'HIVERN (3a Jornada) |
| `resulcllancaments8209` | 2009 | CRITERIUM DE LLANÇAMENTS D'HIVERN |
| `resulcnatlocalcambrils80516` | 2016 | CNAT. LOCAL - CAMBRILS 8-05-16 |
| `resulcnatterritamposta250415` | 2015 | TERRITORIAL AMPOSTA 25‐4‐15 |
| `resulcnatterritpromovalls2411` | 2011 | TERRITORIAL PROMOCIÓ |
| `resulcnatterritsub13equips29111` | 2011 | TERRITORIAL INFANTIL D'HIVERN 10-11 |
| `resulcombinadespalafrugell211213` | 2014 | JORNADA DE PROVES COMBINADES D'HIVERN DE PROMOCIÓ |
| `resulcontrolamposta210215` | 2015 | CONTROL AMPOSTA 21-2-15 |
| `resulcontrolamposta301215` | 2016 | CONTROL D'HIVERN - AMPOSTA 30-12-15 |
| `resulcontrolampposta130216` | 2016 | II CONTROL D'HIVERN - AMPOSTA 13-02-16 |
| `resulcontrolbai-badalona160314` | 2014 | CONTROL BENJAMÍ-ALEVÍ-INFANTIL |
| `resulcontrolbai-elprat150214` | 2014 | CONTROL BENJAMÍ-ALEVÍ-INFANTIL |
| `resulcontrolbai-elprat301113` | 2014 | CONTROL BENJAMÍ-ALEVÍ-INFANTIL |
| `resulcontrolbaielprat70315` | 2015 | CONTROL BENJAMÍ-ALEVÍ-INFANTIL |
| `resulcontrolbenaleinfelprat10613` | 2013 | CONTROL BENJAMÍ-ALEVÍ-INFANTIL |
| `resulcontrolbm140516` | 2016 | I Memorial Josep Novell i Olivé |
| `resulcontrolcadetpc110212` | 2012 | CONTROL CADET MASCULI PISTA COBERTA |
| `resulcontrolcadetpc280112` | 2012 | CONTROL CADET MASCULÍ PISTA COBERTA |
| `resulcontrolcambrils16170515` | 2015 | CONTROL PRIMAVERA 2015 |
| `resulcontrolcambrils240115` | 2015 | CONTROL TERRITORIAL GENER 14-15 |
| `resulcontrolcambrils300116` | 2016 | CONTROL TERRITORIAL GENER 15-16 |
| `resulcontrolcep71114` | 2015 | CONTROL: 20è CONTROL ESPORTIU PENEDÈS |
| `resulcontrolcombi21609` | 2009 | CONTROL DE PROVES COMBINADES |
| `resulcontrolcombinades1920610` | 2010 | CONTROL DE PROVES COMBINADES |
| `resulcontrolfacvac22610` | 2010 | PROVES DE CONTROL |
| `resulcontrolfacvac4709` | 2009 | PROVES DE CONTROL |
| `resulcontrolfcalleida121215` | 2016 | 2n CONTROL FCA PROMOCIO 15/16 |
| `resulcontrolfcavalls19211` | 2011 | CONTROL TERRITORIAL 1 |
| `resulcontroljvjrpr27506serrahima` | 2006 | CONTROL JUVENIL-JUNIOR-PROMESA (2a. Jornada) |
| `resulcontrolmaig150516` | 2016 | CONTROL MAIG 2016 |
| `resulcontrolprimaveracambrils17180514` | 2014 | CONTROL PRIMAVERA 2014 |
| `resulcontrolprimaveracambrils18190513` | 2013 | CONTROL PRIMAVERA 2013 |
| `resulcontrolprimaveracambrils230612` | 2012 | CONTROL PRIMAVERA |
| `resulcontrolprimaveracambrils25410` | 2010 | CONTROL PRIMAVERA |
| `resulcontrolserrahima81215` | 2016 | Festival Inauguració - AAC |
| `resulcontrolterritamposta50316` | 2016 | III CONTROL TERRITORIAL - AMPOSTA 5-3-16 |
| `resulcontrolterritvalls160213` | 2013 | CONTROL TERRITORIAL 2 |
| `resulcontrolvalls250212` | 2012 | CONTROL TERRITORIAL 1 |
| `resulcontrolvalls280515` | 2015 | CONTROLS SOCIALS |
| `resulcontrolvalls50614` | 2014 | CONTROL FACVAC |
| `resulcontrolvalls60216` | 2016 | CONTROL TERRITORIAL |
| `resulcontrolvalls70215` | 2015 | CONTROL TERRITORIAL |
| `resulcontrolvalls80214` | 2014 | CONTROL TERRITORIAL 1 |
| `resulcontrolvic130613` | 2013 | PROVES DE CONTROL |
| `resulcontrolvilanova300416` | 2016 | CONTROL PROMOCIÓ |
| `resulcritveteranssantceloni180715` | 2015 | II CRITERIUM VETERANS BAIX MONTSENY |
| `resulfesthivernserrahima231206` | 2007 | FESTIVAL HIVERN AAC |
| `resulgpmarxasantcugat80516` | 2016 | I GRAN PREMI DE MARXA "CIUTAT DE SANT CUGAT" |
| `resulinauguraciobarbera21407` | 2007 | 1er. FESTIVAL ATLÈTIC BARBERÀ |
| `resullliguetasub11bcn71115` | 2016 | 3a. LLIGUETA ATLÈTICA DE BARCELONA SUB-11 |
| `resulmemorialuribe5708` | 2008 | 10è Memorial LLUÍS URIBE |
| `resulmitingveteransbm40616` | 2016 | IV Meeting d'Atletisme Veterans |
| `resulmitingveteransgava220516` | 2016 | 4t Meeting de Veterans "Ciutat de Gavà" |
| `resulontrolvilanova51215` | 2016 | CONTROL DINAMI-K PROVES DE PC |
| `resulpromoterritinfantilcambrils9208` | 2008 | TERRITORIAL INFANTIL D'HIVERN 07-08 |
| `resulreus22106` | 2006 | IV CONTROL HIVERN - Reus 220106 |
| `resulreus2509` | 2009 | Lliga Catalana Promoció - Jornada 9 |
| `resultat-20170311-gpmarxasantcugat` | 2017 | II Gran Premi de Marxa "Ciutat de Sant Cugat" |
| `resultat-20170318-gpmarxagava` | 2017 | 1r. Gran Premi de Marxa "Ciutat de Gavà" |
| `resultat-20170407-gpmarxasantcugat` | 2018 | III Gran Premi de Marxa "Ciutat de Sant Cugat" |
| `resultat-20170409-catclubsgrupalleida` | 2017 | Grup A Cnat.Catalunya/Crit.Clubs-1a jorn.classif. |
| `resultat-20170422-catclubsgrupaamposta` | 2017 | Grup A Cnat.Catalunya/Crit.Clubs-2a jorn.classif. |
| `resultat-20170521-mitingveteransgava` | 2017 | 5è. Meeting Veterans "Ciutat de Gavà" |
| `resultat-2017060304-catjunjuvprolloret` | 2017 | CAMPIONAT DE CATALUNYA JUVENIL |
| `resultat-20180224-trofeuhivernreus` | 2018 | Trofeu d hivern 2018 |
| `resultat-20180407-catmeridionalguipuzcoacambrils` | 2018 | VI Trobada Catalunya Meridional - Gipuzkoa |
| `resultat-20180421-trobadaoccitaniacambrils` | 2018 | II Trobada Cambrils - Occitània |
| `resultat-20180506-catclubsfinalbsabadell` | 2018 | Final Cnat Catalunya Clubs. Grup "B" |
| `resultat-20181209-trofeusalcedacastellscambrils` | 2018 | 51è Trofeu Salceda i Castells - 7è In Memoriam |
| `resultat-20190323-controlfcapromociolleida` | 2019 | 3r CONTROL FCA PROMOCIO 18/19 |
| `resultat-20190406-gpmarxasantcugat` | 2019 | IV Gran Premi de Marxa "Ciutat de Sant Cugat" 2019 |
| `resultat-20190427-trobadacatmeridionalguipuzcoacambrils` | 2019 | VII Trobada Catalunya Meridional - Gipuzkoa |
| `resultat-20190511-meetingveteransmarbella` | 2019 | XIV Meeting Català de Veteranes i Veterans - II Memorial Valentí Huch |
| `resultat-20190518-catclubssub12elprat` | 2019 | Cnat. Catalunya Clubs Sub12 Masculí |
| `resultat-20190518-catclubssub14elprat` | 2019 | Cnat. Catalunya Clubs Sub14 Masculí |
| `resultat-20190519-catclubssub10elprat` | 2019 | Cnat. Catalunya Clubs Sub10 Masculí |
| `resultat-20190519-catclubssub16elprat` | 2019 | Cnat. Catalunya Clubs Sub16 Masculí |
| `resultat-20190519-mitingmastergava` | 2019 | 6è Meeting Màster «Ciutat de Gavà» |
| `resultat-20190615-trobadacambrilsandorra` | 2019 | II Trobada Cambrils - Andorra |
| `resultat-20200118-controlgenerreus` | 2020 | control Gener 2 |
| `resultat-20210123-catclubsbpcbcnpsj` | 2021 | CAMPIONAT CATALUNYA CLUBS B MASCULINS - PC |
| `resultat-20210214-catllancamentshivernsabadell` | 2021 | Cnt.Catalunya Llançaments d´hivern Absolut i Sub20 |
| `resultat-20210227-controllleida` | 2021 | 1R control d´Atltisme Temporada 2021 |
| `resultat-20210404-cat10000santacoloma` | 2021 | Cnt Catalunya de 10.000 Absolut, Sub23 i Master i de 5.000 Sub20 i Sub18 |
| `resultat-2021041718-cnatterritcombinadestarragona` | 2021 | Cnt.Territorial Proves Combinades |
| `resultat-20210501-trofeuesparrecsgava` | 2021 | 8è Trofeu Promoció Baix Llobregat - Gran Premi Fira dels Espàrrecs |
| `resultat-20210529-controllleida` | 2021 | 2n control d´atletisme 2021 |
| `resultat-20210605-controllleida` | 2021 | 3r control delegació de Lleida |
| `resultat-20211218-trofeunadalcnrp` | 2021 | Trofeu Nadal d´Atletisme |
| `resultat-20211218-trofeunadallleida` | 2021 | I Trofeu de Nadal “Memorial Juan Méndez” |
| `resultat-20220327-memorialcassielprat` | 2022 | Criterium de llançaments - I Memorial Llorenç Cassi |
| `resultat-20220527-mitingmollet` | 2022 | V Mítin Internacional Ciutat de Mollet del Vallès |
| `resultat-20220603-trofeuprimaveraamposta` | 2022 | Trofeu Primavera |
| `resultat-20220611-meetinglloretdemar` | 2022 | Acerko Meeting Lloret de Mar |
| `resultat-20230129-criteriumllancamentssantacoloma` | 2023 | Criterium de Llançaments Llargs d'hivern Absolut - Sub23 |
| `resultat-20230618-meetingveteransesmarbella` | 2023 | XVII Míting Català de Veteranes i Veterans |
| `resultat-20231230-cat10000marxamaster` | 2023 | Cnt Catalunya de 10.000 metres marxa en pista Màster |
| `resultat-20241201-copapromociopcsabadell` | 2024 | Copa Femenina de Promoció |
| `resultat-20241207-controlabsolutpcsabadell` | 2024 | 2n control Absolut ST 2024-2025 |
| `resultat-20241207-controlsub1820pcsabadell` | 2024 | 1r control sub18 i sub20 ST |
| `resultat-20241213-controlabsolutpcsabadell` | 2024 | 4t control Absolut ST 2024-2025 |
| `resultat-20241214-controlsub16pcsabadell` | 2024 | 1a jornada control sub16 PC |
| `resultat-20241215-controlsub1820pcsabadell` | 2024 | 2n control sub18 i sub20 ST |
| `resultat-20241215-trofeunadalcnrp` | 2024 | Trofeu Nadal |
| `resultat-20241220-controlabsolutpcsabadell` | 2024 | 5è control Absolut ST 2024-2025 |
| `resultat-20241222-controlabsolutpcsabadell` | 2024 | 6è control Absolut ST 2024-2025 |
| `resultat-20250117-controlabsolutpcsabadell` | 2025 | 8è control Absolut ST 2024-2025 |
| `resultat-20250119-controlsub1820pcsabadell` | 2025 | 3r control sub18- i sub20 ST |
| `resultat-20250215-territorialcombinadessub1214tarragona` | 2025 | CAMPIONAT TERRITORIAL DE TARRAGONA DE PROVES COMBINADES D'HIVERN S12 i S14 |
| `resultat-20250406-catclubsmarxasantacoloma` | 2025 | 42è Ct Catalunya Clus de Marxa Masculí, Femení i Mixte |
| `resultat-20250412-territorialpromocioasco` | 2025 | 1a jornada Cnt Territorial s10 s12 s14 s16 |
| `resultat-20250517-gpmigfonsfonscontrolfcagranollers` | 2025 | Gran Premi de Mig Fons, Fons i proves de control |
| `resultat-20251025-trofeupromociosantacolomamati` | 2025 | Trofeu Promoció 2025 (1ª jornada) |
| `resultat-20251025-trofeupromociosantacolomatarda` | 2025 | Trofeu Promoció 2025 (2ª jornada) |
| `resultat-20260322-controltorredembarra` | 2026 | IX Jornades Atlètiques Torredembarra |
| `resultat-20260606-granpremisantacoloma` | 2026 | Gran Premi d'Aire Lliure |
| `resultat-20261017-trofeupromocio1tarragona` | 2026 | Trofeu Promoció 2026 (1ª jornada) |
| `resulterritinfantilcambrils20213` | 2013 | TERRITORIAL INFANTIL D'HIVERN 12 - 13 |
| `resulterritsub13equipscambrils210112` | 2012 | TERRITORIAL INFANTIL D'HIVERN 11-12 |
| `resultrobadaandcatmercambrils180616` | 2016 | II TROBADA CAT. MERIDIONAL - ANDORRA 15 - 16 |
| `resultrobadaandorra180513` | 2013 | XXI TROBADA INTL. D'ATLETES VETERANS |
| `resultrobadabenjami14608` | 2008 | TROBADA CATALANA BENJAMÍ |
| `resultrobadacambrils60413` | 2013 | I TROBADA GIPUZKOA - CAT. MERIDIONAL 12 - 13 |
| `resultrobadacambrilsoccitania240415` | 2015 | I TROBADA CAMBRILS - OCCITÀNIA 14-15 |
| `resultrobadacatmeridguipuzcoacambrils110415` | 2015 | III TROBADA CAT. MERIDIONAL - GIPUZKOA 14-15 |
| `resultrobadatardorcambrils171112` | 2013 | X TROBADA TARDOR 12 - 13 |
| `resultrobadatardortarragona201110` | 2011 | VIII TROBADA TARDOR 10 - 11 |
| `resultrobadatgnaguipuzcoa260414` | 2014 | II TROBADA CAT. MERIDIONAL - GIPUZKOA 13-14 |
| `resultrofeuaperturasabadell25410` | 2010 | FESTIVAL D'APERTURA AL AIRE LLIURE A CATALUNYA |
| `resultrofeucalsmarxa30116` | 2016 | XXII Trofeu Marxa Rossend Cals / XI Torfeu Mar Gomez-Joaquim Risueño |
| `resulveteranserrahima12507` | 2007 | CONTROL DE VETERANS - SERRAHIMA 12 MAIG 2007 |

No name in the table above was normalised, translated, title-cased or combined
with the venue: each is a single header line as the sheet prints it.
