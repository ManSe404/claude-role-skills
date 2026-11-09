# Plan: pack `ai-architect`

Status: predlog od 2026-11-07, ništa nije napravljeno. Na kraju su odluke koje čekaju Stefana.

## Cilj

Pack za AI solutions architect-a. Pre nego što se bilo šta gradi, pack odlučuje šta rešenje treba da
bude: bez LLM-a, jedan poziv modela, ceo korpus u kontekstu, RAG, agentic RAG, workflow, jedan agent
ili orkestrator sa podagentima. Bira alate po slojevima, sa cenom na stvarnom obimu, crta
interaktivnu arhitekturu i pregleda postojeća AI rešenja.

Format je isti kao u packu software-engineering:
- SKILL.md po kalupu (posao, ulaz, koraci, izlaz, čita, piše, nikad);
- skripte broje;
- stranica je JSON koji crta `render_page.py`.

Van obima su pokretanje evala, analiza grešaka, podešavanje retrievala i pregled trace-ova (Langfuse).
To ide u kasniji pack `ai-engineering`.

Javno ne postoji ništa što spaja odluku i stranicu (pretraga od 2026-11-06). Najbliži delovi:
- bowen31337/claude-solution-architect (MIT): redosled odluka;
- alirezarezvani/claude-skills, agent-designer i rag-architect (MIT): tabela obrazaca i provere za RAG;
- konraddzbik/architecture-diagram-skill (MIT): klikabilan tok kroz dijagram.

Preuzimamo ideje, ne kod.

## Skillovi

### 1. `ai-pattern`: koji obrazac

Kada: stigne nov AI slučaj ili brief klijenta, pre bilo kakve gradnje.
Ulaz: brief (tekst ili fajl), a opciono i folder sa dokumentima ili repo.

Koraci:
1. **Okvir:** korisnici, posao, obim, kriterijumi uspeha i ono o čemu se ne pregovara (regulativa,
   gde podaci smeju da budu, SLA, budžet). Ako fale činjenice koje bi promenile odluku, pita za 2–4
   najvažnije. Ako korisnik kaže „nastavi“, svaka pretpostavka ide na stranicu zajedno sa odlukom
   koju pokreće.
2. **Podela posla:** za svaki korak odluči da li ga radi model, postojeći sistem ili čovek, i zašto.
3. **Dokumenti, ako ih ima:** `corpus_stats.py`. Staje li sve u kontekst? Koliko često se menja?
4. **Tvrda pravila:** `decide.py`. Primeri: za živo stanje treba poziv alata, ne retrieval; kad je
   greška skupa a čoveka nema, autonomni agent otpada.
5. **Ostale opcije, po redu:** predvidljivost → cena greške → vidljivost → latencija → cena. Prvi
   faktor koji isključi opciju odlučuje i dobija ime (vezujući uslov).
6. **Lestvica:** kreće od najjednostavnije opcije i penje se samo kad niža padne na imenovanom zahtevu.
7. **Šta bi promenilo odluku:** 3–5 uslova (obim 10×, upis u ERP, nov jezik…).
8. **Kriterijumi prihvatanja:** 3–5 metrika, svaka sa pragom i načinom merenja.
9. **ADR (Nygard):** nacrt kao blok koda za kopiranje; u repo ide samo uz „da“.
10. **Stranica.**

Na stranici:
- verdict: izabrani obrazac i vezujući uslov;
- `decision` blok: opcije × faktori, uz svaku odbačenu opciju i razlog;
- graf podele posla;
- pretpostavke, šta bi promenilo odluku, kriterijumi i ADR.

Nikad:
- ne predlaže agenta kad workflow zadovoljava;
- ne navodi cenu ili verziju modela bez datuma i izvora;
- ne šalje brief van mašine.

### 2. `ai-stack`: kojim alatima

Kada: obrazac je izabran i treba izabrati alate.
Ulaz: JSON stranice `ai-pattern` ili opis obrasca, plus ograničenja (oblak klijenta, gde podaci
smeju da budu, on-prem).

Koraci:
1. **Slojevi:** model po koraku, embedding, vektorsko skladište, framework (ili bez njega), hosting,
   tracing, eval i guardrails.
2. **Kandidati:** za svaki sloj 2–3 kandidata po kriterijumima iz `references/stack.md`. Uz izbor ide
   i šta smo time odbacili.
3. **Varijante:** najviše dve, na primer Azure-native i lokalno/otvoreno.
4. **Cena i latencija:** za svaku varijantu iz `cost_model.py`, uz tabelu cena sa datumom i izvorom.
5. **Vezivanje za dobavljača:** rizici i šta bi koštao prelazak.
6. **Pre ponude:** šta treba proveriti (kvote, region, dostupnost modela).

Nikad:
- cena iz memorije;
- mrežni upit bez dozvole.

### 3. `ai-architecture`: interaktivna stranica

Kada: AI rešenje treba pokazati klijentu ili timu, iz dizajna ili iz repoa.
Ulaz: JSON od `ai-pattern` i `ai-stack`, opis, ili repo (tada `ai_inventory.py`).

Koraci:
1. **Komponente po zonama:** korisnik i kanal, aplikacija, AI sloj, znanje, sistemi i alati, operacije.
2. **Veze i tokovi:** veze među komponentama i 2–4 toka zahteva korak po korak.
3. **Granice poverenja:** gde ulazi tekst kome ne verujemo (korisnik, dokumenti, izlaz alata) i do
   kojih alata sa posledicama može da stigne.
4. **Varijante:** na primer RAG ↔ agentic RAG, kao prekidač.
5. **Detalji komponente:** tehnologija, odgovornost, podaci, šta se desi kad padne, udeo u ceni.

Nikad:
- komponenta iz repoa koju nije pročitao dobija oznaku [guess];
- ne prikazuje tajne ni vrednosti konfiguracije, samo imena.

### 4. `ai-review`: pregled postojećeg AI rešenja

Kada: pre releasea, pri preuzimanju projekta ili pre predaje klijentu.
Ulaz: repo ili dizajn dokument.

Koraci:
1. Pokreni `ai_inventory.py` i iz njega rekonstruiši arhitekturu.
2. Prođi listu iz `references/anti-patterns.md`:
   - obrazac je prevelik za problem;
   - živo stanje ide preko retrievala;
   - agent nema limit koraka ni troška;
   - izlaz alata ili dokumenta stiže do alata sa posledicama bez čoveka (prompt injection);
   - ključ je u kodu;
   - nema evala ni tracinga;
   - pozivi modela nemaju timeout ni fallback;
   - lični podaci idu ka spoljnom modelu;
   - model nije zakucan;
   - cena na obimu nije procenjena.
3. Svaki nalaz dobija file:line i predlog.
4. Na grafu se označe problematična mesta.

Nikad:
- ne menja ništa;
- ne pokreće aplikaciju;
- ne zove modele.

## Skripte

Sve skripte su Python stdlib, samo čitaju i pišu JSON na stdout.

| skripta | skill | šta radi |
|---|---|---|
| `corpus_stats.py` | ai-pattern | fajlovi po tipu, veličine, procena tokena (chars/4, uz napomenu), raspon izmena, duplikati po hešu, latinica ili ćirilica, gruba procena broja strana PDF-a |
| `decide.py` | ai-pattern | ulaz su činjenice iz briefa kao JSON (živo stanje, poznati koraci, cena greške, čovek u petlji, budžet latencije, obim, tokeni korpusa, akcije sa posledicama); izlaz kaže koje opcije padaju i po kom pravilu. Samo tvrda pravila, težinu odlučuje Claude |
| `cost_model.py` | ai-stack | koraci × pozivi × tokeni × cena × obim, udeo keša, p50 latencija za sekvencijalne i paralelne korake. Tabela cena je fajl sa datumom i izvorom; `prices.example.json` je označen kao primer koji treba proveriti |
| `ai_inventory.py` | ai-architecture, ai-review | Python, C# i TypeScript: SDK-ovi (openai, anthropic, Azure.AI.OpenAI, langchain, langgraph, llama_index, semantic_kernel, ollama…), imena modela, vektorska skladišta, definicije alata, promptovi, limiti petlji, timeouti, tracing, evali. Za env promenljive samo imena, nikad vrednosti. Sve sa file:line |

## Renderer (`shared/`, menja stranice svih packova)

Dva nova tipa bloka.

**`decision`:** opcije × faktori.
- Svaka ćelija je pass, weak ili fail, sa kratkim tekstom.
- Svaka opcija ima status chosen, viable ili eliminated, uz `eliminated_by` i `why`.
- Izabrana opcija je istaknuta, a odbačene su prigušene sa vidljivim razlogom.

**`architecture`:**
- Polja:
  - `zones`;
  - `components` {id, label, zone, kind, tech, note, details, variants};
  - `links` {from, to, label, trust: trusted | untrusted, variants};
  - `flows` [{id, title, steps: [{from, to, text}]}];
  - `variants` [{id, label, note}].
- Interakcija:
  - klik na komponentu otvara panel sa detaljima i vezama;
  - tok se pušta ili korača strelicama ←/→;
  - prekidač menja varijantu;
  - prikaz granica poverenja se uključuje i isključuje;
  - linkovi `#component=`, `#flow=…&step=` i `#variant=` otvaraju stranicu u tom stanju.
- Bez JS-a i pri štampi: tabela komponenti, tokovi kao `steps`, varijante kao liste.
- Raspored:
  - računa se u Pythonu i uvek je isti: zona je kolona u fiksnom redu, komponente su složene jedna
    ispod druge;
  - koristi postojeće helper-e za graf.
- Ograničenja: bez biblioteka, ništa sa mreže, svaka vrednost je escapovana, stranica sa fontovima
  ispod ~400 KB.

Testovi:
- greške validacije sa JSON putanjom;
- escapovanje;
- isti JSON daje isti HTML;
- nijedan spoljni URL;
- svaka veza, tok i varijanta pokazuje na postojeći id.

**Preduslov:** sinoćne nekomitovane izmene renderera (14 fajlova, +1144 linije, 2026-11-06 23:08)
se prvo komituju, jer ovaj pack gradi na njima.

## Fixture: `fixtures/acme-assist/` (sve izmišljeno)

**`brief-support.md`:** asistent za podršku izmišljenog proizvođača uređaja.
- Priručnici i FAQ su stabilno znanje, a status porudžbine iz ERP-a je živo stanje.
- Povraćaj robe ide po pravilima.
- Srpski i engleski, 3.000 pitanja dnevno, a pogrešan odgovor o garanciji je skup.
- Ispravan odgovor je workflow sa rutiranjem: RAG za priručnike, poziv alata za porudžbine, čovek
  za povraćaj. Autonomni multi-agent otpada.

**`brief-tagging.md`:** 200 mejlova dnevno u 6 kategorija. Ispravan odgovor je jedan poziv modela sa
strukturiranim izlazom. Ovaj brief proverava da skill ne preteruje.

**`corpus/`:** 15–25 malih dokumenata (md, txt, nekoliko minimalnih PDF-ova), latinicom i ćirilicom.

**`files/` + `history.py`:** mala Python aplikacija sa 8 podmetnutih problema za `ai-review`:
1. stanje zaliha čita iz vektorske baze, pa je zastarelo;
2. petlja agenta nema limit;
3. izlaz web alata ide u alat za slanje mejla bez potvrde;
4. lažni podrazumevani ključ (`sk-example-…`) u `config.py`;
5. nema evala;
6. pozivi modela nemaju timeout;
7. koristi alias modela umesto zakucane verzije;
8. nema tracinga.

Spisak ide i u test.

## Evali (`claude plugin eval`)

1. **pattern-does-not-overbuild:** za brief-tagging bira jedan poziv modela, bez agenta.
2. **pattern-live-state:** za brief-support živo stanje ide preko alata, ne retrievala, i vezujući
   uslov ima ime.
3. **stack-cost-from-script:** brojevi na stranici su izlaz `cost_model.py`, a cene imaju datum.
4. **architecture-page:** HTML postoji, ima tok i varijantu, nema spoljnih URL-ova, a nepoverljiv
   ulaz je označen.
5. **review-finds-planted:** nalazi bar 6 od 8 podmetnutih problema i ne menja nijedan fajl.

Svaki slučaj ima i grader `skill-fired`. Evali se pokreću samo na Stefanov zahtev. Za poređenje: pet
headless pokretanja u packu software-engineering koštalo je $6.55.

## Ostalo

- `roles/ai-architect.md`, CLAUDE.md starter:
  - lestvica „najjednostavnije što zadovoljava“;
  - oznake [high], [med] i [guess];
  - promenljive činjenice (cene, modeli, kvote) uvek sa datumom i izvorom;
  - podaci klijenta nikad u primerima.
- `references/patterns.md`, `stack.md` i `anti-patterns.md`: kratko, bez cenovnika.
  - Izvori: Anthropic „Building effective agents“, bowen31337 i alirezarezvani (MIT).
  - Prilagođen tekst ide u THIRD-PARTY-NOTICES.
- Opisi skillova ne smeju da preotmu zahteve od `engineering:architecture`,
  `engineering:system-design`, `claude-api` i `langfuse`. Svaki opis kaže „AI/LLM rešenje“, kao i
  „pre gradnje“ ili „pregled postojećeg“.
- Stranica je na jeziku zahteva. Fontovi imaju Latin Extended, a ćirilicu nemaju, pa se srpske
  stranice pišu latinicom.
- Ažurirati README tabelu, unos u marketplace-u, `plugin.json` i CLAUDE.md repoa (tamo sada piše
  „samo SWE pack“).

## Redosled

- M0: komit postojećih izmena (Stefan).
- M1: references, fixture i testovi fixture-a.
- M2: renderer (`decision`, `architecture`), testovi, `tools/sync_shared.py`.
- M3: četiri skripte i testovi na fixture-u.
- M4: četiri SKILL.md i `references/example.json`, napravljeni headless pokretanjem na fixture-u i
  ručno provereni (~$5–10).
- M5: evali napisani; pokreću se samo na zahtev.
- M6: README, marketplace, role starter i notices. Na kraju zeleno: pytest, ruff, mypy strict,
  `claude plugin validate .`.

## Odluke koje čekaju Stefana

1. Ime packa `ai-architect`?
2. Četiri skilla, a evali, retrieval i trace review idu u kasniji pack `ai-engineering`?
3. `decide.py` sa tvrdim pravilima: da ili ne?
4. Stack podrazumevano neutralan, sa Azure-om i lokalnim Ollama-om kao dve varijante?
5. Komit sinoćnih izmena pre početka.
