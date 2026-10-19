# Sincronizzazioni unificate e destinazioni ordinate

Data: 19 ottobre 2026. Base dell'analisi: `master`, commit `2f22840`.
Branch di preparazione: `feat/unified-sync-hierarchy`.

## Stato e autorizzazione

Questo documento salva l'analisi richiesta dall'utente per una futura
implementazione. Il lavoro attuale comprende soltanto branch e documentazione:
nessuna modifica a interfaccia, motore, configurazione o installazione.

L'utente ha proposto una gerarchia scelta da lui, senza dividere locale e cloud:
upload su tutte le destinazioni selezionate e download in ordine di priorità,
per esempio Google Drive e, se la copia non esiste, OneDrive online.
Ha chiesto di conservare l'analisi e rimandare l'implementazione a una richiesta
successiva. Le raccomandazioni e le questioni aperte sotto non costituiscono
ancora un contratto eseguibile approvato.

## Problema attuale e riferimenti

- `ui/pages/folders.py`: coppie di cartelle locali, inclusa la cartella OneDrive
  gestita dal client desktop; schede, ricerca, filtro e procedura di aggiunta.
- `ui/pages/cloud_sync.py`: attività su connessioni dirette; elenco, modulo di
  modifica, operazioni manuali e ripristino delle copie di sicurezza cloud.
- `ui/pages/connections.py`: accesso ai servizi, identità degli account e cartella
  radice autorizzata; questa funzione rimane distinta dalla gestione delle attività.
- `ui/main_window.py`: navigazione separata per Folders e Cloud Sync.
- `src/config.py`, `src/cloud_models.py`: modelli distinti per coppie locali,
  connessioni e attività cloud; oggi ogni attività cloud ha una connessione.
- `backend/services/sync_service.py`, `src/cloud_sync.py`: coordinamento,
  direzioni configurate, esecuzioni pianificate, recupero del lavoro pendente,
  protezioni e modalità bidirezionale.
- `docs/cloud-sync.md`, `docs/contracts/cloud-sync.md`: comportamento attuale,
  copie di sicurezza, credenziali e vincoli da preservare o modificare esplicitamente.

Le due pagine presentano lo stesso compito con parole, strutture e procedure
diverse. Unificarle soltanto visivamente non realizza la nuova richiesta:
l'upload multiplo e il download con fallback cambiano anche modello ed esecuzione.

## Direzione proposta dall'utente

Una sincronizzazione rappresenta:

1. Un nome comprensibile, per esempio Salvataggi gioco.
2. Una cartella sul PC.
3. Una o più destinazioni scelte esplicitamente dall'utente.
4. L'abilitazione di ciascuna destinazione per l'upload.
5. L'ordine delle sorgenti da consultare durante il download.

La destinazione può essere un account cloud oppure una cartella locale o di rete.
La stessa posizione è destinazione durante l'upload e sorgente durante il
download. Il tipo di collegamento appare come informazione, senza determinare
la pagina in cui lavorare. "Tutte" significa tutte le destinazioni abilitate
per quella sincronizzazione, non tutti gli account collegati all'applicazione.

Esempio di rappresentazione, con dati fittizi:

```text
Salvataggi gioco
Cartella sul PC: C:\Giochi\Esempio\Saves

Destinazione                         Upload    Priorità download
Google Drive · player@example.test     sì             1
OneDrive online · player@example.test  sì             2
NAS · \\server\backup                 sì             3
```

## UX/UI raccomandata

- Un'unica voce di navigazione, Sincronizzazioni, con elenco ricercabile e filtri
  per stato o destinazione. Nessuna seconda suddivisione locale/cloud.
- Un solo pulsante Aggiungi sincronizzazione. Percorso di creazione: cartella
  sul PC, scelta delle destinazioni e loro percorsi, ordine di download,
  riepilogo. Nome suggerito dalla cartella; dettagli tecnici in Opzioni avanzate.
- Connections conserva la gestione degli account. Dalla creazione si può
  raggiungere il collegamento di un servizio mancante senza reinserire i dati.
- Ogni elemento mostra nome, percorso sul PC, destinazioni, stato complessivo
  e ultima esecuzione. Il dettaglio mostra risultati e aggiornamento per destinazione.
- Azioni esplicite: Invia alle destinazioni e Scarica sul PC; indicazione della
  sorgente effettivamente usata. Le etichette devono corrispondere all'operazione
  reale, anche in presenza delle attuali direzioni globali configurabili.
- Riordino accessibile con trascinamento e comandi Sposta su/Sposta giù,
  utilizzabili da tastiera. Stato espresso con testo oltre al colore.
- Feedback leggibile: "Aggiornate 2 destinazioni su 3" oppure
  "Scaricato da OneDrive: copia assente su Google Drive".
- Rimozione di un'attività o di una destinazione distinta dalla cancellazione
  dei file. Mantenere le conferme e le protezioni esistenti.

Due organizzazioni possibili sono elenco unico con filtri o gruppi per servizio.
Si raccomanda l'elenco unico: un'attività con più servizi non deve comparire più
volte né obbligare a scegliere un servizio per essere trovata.

## Regole di esecuzione raccomandate, da definire prima del codice

### Upload su più destinazioni

Registrare un risultato distinto per destinazione e un risultato complessivo
che distingua riuscita completa, parziale e fallimento. Un guasto a un servizio
non deve essere nascosto dal successo di un altro. Valutare la prosecuzione
sulle destinazioni indipendenti quando il problema riguarda solo un servizio;
annullamento o problemi alla sorgente possono richiedere l'arresto dell'intera
operazione. Il recupero deve riconoscere le destinazioni rimaste incomplete.

Per dichiarare che più copie appartengono allo stesso aggiornamento occorre
verificare la coerenza dei file letti: l'applicazione che li modifica potrebbe
scrivere durante gli upload. Non promettere una transazione atomica tra servizi
o coordinamento tra più PC.

### Download ordinato e fallback

Si raccomanda di selezionare una sola sorgente per l'intera attività. Il fallback
file per file potrebbe mescolare versioni incompatibili di uno stesso salvataggio.
L'assenza di un singolo file non deve completare automaticamente la cartella con
file recuperati da altri servizi.

Distinguere almeno: copia assente, cartella vuota, copia incompleta, servizio
irraggiungibile, autorizzazione scaduta e conflitto. Una lista remota fallita non
prova che la copia sia assente. Una cartella esistente non prova che sia completa.

L'ordine scelto non equivale alla data più recente. Se l'ultimo upload riesce su
OneDrive ma fallisce su Google, la prima destinazione può contenere una versione
precedente. Occorre definire come riconoscere e presentare questa condizione,
inclusi dati preesistenti senza metadati e aggiornamenti fatti da altri PC.

Se tutte le sorgenti sono assenti o inutilizzabili, mostrare un risultato esplicito
e preservare i dati sul PC. Definire il comportamento anche in caso di errore a
download iniziato, evitando di mescolare silenziosamente sorgenti diverse.

## Decisioni ancora aperte

1. Fallback solo per copia assente oppure anche per servizio irraggiungibile?
   Raccomandazione iniziale: assenza accertata; errori espliciti e opzione separata
   per il fallback su indisponibilità.
2. Priorità assoluta oppure salto delle copie certamente meno recenti/incomplete?
   Raccomandazione: rendere riconoscibile la versione e richiedere una scelta
   esplicita prima di usare una copia nota come precedente.
3. Come definire una copia valida e completa? Quali metadati, identificatori
   di aggiornamento e verifiche funzionano anche tra PC diversi?
4. L'utente può escludere una destinazione dal download mantenendo l'upload?
   L'interfaccia deve rappresentare questa scelta se viene introdotta.
5. Come interagiscono upload multiplo, lavoro pendente e una richiesta di download?
   Non eliminare né aggirare implicitamente le attuali protezioni di recupero.
6. Come convivono gerarchia e modalità bidirezionale esistente? Non estendere
   automaticamente il confronto tra due lati a un confronto tra tutti i servizi.
7. Come tradurre i pulsanti e le esecuzioni automatiche rispetto alle direzioni
   startup/shutdown oggi configurabili? Evitare etichette che promettono upload
   quando il motore esegue il contrario.

## Compatibilità e confini

- Conservare cartelle, connessioni, credenziali, cronologia, pianificazioni,
  percorsi, stato di recupero e impostazioni di sicurezza già presenti.
- Preparare una migrazione esplicita prima di cambiare lo schema. Non aggregare
  automaticamente vecchie attività solo perché condividono un nome o un percorso:
  la loro equivalenza deve essere verificata.
- Conservare dry run, verifica, soglie di sicurezza, lock condiviso e comportamento
  senza propagazione delle cancellazioni; ogni modifica richiede una decisione.
- Backup ZIP locali e snapshot cloud hanno ripristini diversi. Un punto di accesso
  coerente deve conservarne posizione, natura e modalità di recupero riconoscibili.
- Non modificare registrazioni OAuth, numero di account per servizio o credenziali
  per realizzare questa UX. Non copiare dati privati nel branch o nei test.
- Non avviare trasferimenti reali né aggiornare l'installazione durante la preparazione.

## Criteri osservabili per la futura implementazione

- Esiste un solo punto per creare, trovare, modificare e avviare un'attività.
- Un'attività può includere cloud e cartelle locali/rete senza essere duplicata.
- L'upload raggiunge tutte le destinazioni abilitate; risultati parziali e retry
  sono riconoscibili per singola destinazione.
- Il download rispetta l'ordine salvato e spiega quale sorgente ha usato e perché.
- I casi copia assente, autorizzazione fallita, servizio offline, copia incompleta,
  versione precedente e nessuna sorgente disponibile hanno esiti distinti.
- Un fallback non compone implicitamente la cartella da versioni di servizi diversi.
- Impostazioni avanzate, stato in corso, annullamento, errore e ripristino sono
  accessibili e comprensibili anche da tastiera.
- Configurazioni preesistenti continuano a essere utilizzabili secondo una
  migrazione verificata; nessun file o backup è eliminato dalla sola migrazione.

## Ripresa del lavoro

Quando l'utente richiederà l'implementazione: verificare il codice aggiornato,
risolvere le decisioni aperte che cambiano il comportamento, consolidare questo
documento in un design approvato e preparare piano, contratto e migrazione
proporzionati al cambiamento. Verificare poi motore e UI con dati sintetici,
coprendo successi parziali, fallback e recupero prima di usare account reali.
