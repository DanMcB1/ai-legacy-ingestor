# Unstructured Legacy Ingestor

**Portfolio project #3 of 12** from [@suraj_sharma14's FDE project list](https://x.com/suraj_sharma14/status/2125197762752806998).

A small, offline demo that turns **messy legacy sources** — crooked scans of old forms, a mainframe extract, a messy spreadsheet, and a plain memo — into a **clean, chunked, searchable store**, with a citation back to the source file, page, or record.

This is a **portfolio demo**, not production software. The documents are **sample data**. The app does not connect to a real DMS, filing cabinet, or document-management system, and it does not send data to a paid API.

Built for **Daniel McBrearty** as part of a Forward Deployed Engineer / solutions engineer portfolio. The sample company is **Lakeside Auto Group (sample)**, the same fictional mid-size dealer group used in the other portfolio demos.

## Why this matters for FDE work

Customer data is never clean. Week one of most AI deployments is not "pick a model." It is data wrangling.

A Forward Deployed Engineer is often the person who has to say that out loud, then prove the files can be read at all. In a dealership the week-one pile looks familiar:

- paper deal jackets and repair orders that were scanned crooked in 1998
- a fixed-width extract from an old DMS, still in EBCDIC, with packed-decimal (COMP-3) amounts
- a spreadsheet someone exported with three date formats and two header rows
- a memo that mentions a VIN the system of record never got

If you load that pile into a chatbot and hope, you cannot answer a basic question: *where did this number come from?* This demo does the unglamorous work first:

- detect the file type
- extract it (Tesseract OCR with deskew and thresholding; a COBOL copybook parser; CSV/Excel cleanup)
- normalize dates, currency, VINs, and names
- chunk the result in a structure-aware way
- index it locally, with **provenance** on every passage
- publish a **data-quality report**: what parsed, what was rejected, and what a person should review

That report is the start of a customer conversation, not a footnote.

## Quick start

You need Python 3.10+ (3.13 is fine). For the scanned-form samples you also need [Tesseract OCR](https://github.com/tesseract-ocr/tesseract). No account, no cloud key, no internet after the packages are installed.

On Debian or Ubuntu:

```bash
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng
```

Then:

```bash
git clone https://github.com/DanMcB1/ai-legacy-ingestor.git
cd ai-legacy-ingestor
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Or: `./run.sh`

The app opens in your browser (usually [http://localhost:8501](http://localhost:8501)).

- The default view **ingests the bundled samples** and searches for Anita Rosales's warranty claim.
- Each hit cites the source file, the page or record, and — for scans — the OCR confidence.
- Open **Pipeline** to walk one file from raw, through extracted and cleaned, to the chunks that were indexed. The scanned forms show the image next to the raw extract.
- Open **Quality report** to see the five rejected records (a smashed packed-decimal field, a truncated mainframe row, an unparseable spreadsheet amount, and so on) and the scans flagged for a person to review.
- You can switch to a single bundled sample in the sidebar, or upload your own files. For a mainframe extract, upload the `.DAT` and its `.CPY` copybook together.

The same pipeline runs from the command line:

```bash
source .venv/bin/activate
python -m ingestor generate
python -m ingestor ingest
python -m ingestor search "warranty claim for Anita Rosales"
python -m ingestor report
```

To run the checks (COMP-3 / EBCDIC decoding, date and currency normalization, chunking, provenance, and search citations):

```bash
python -m unittest discover -s tests
```

A saved example of a search with citations is in [`examples/search-anita-rosales.md`](examples/search-anita-rosales.md).

## What's in the sample set

All of it is fictional, labeled as sample data for Lakeside Auto Group:

- **Scanned forms** (JPEG and PDF), rendered to look like 1990s paperwork and then skewed and noised so OCR has real work to do:
  - a Lakeside Honda repair order for Marcus Webb (`RO-184422`, 2018 Civic)
  - a Lakeside Toyota F&I deal recap for Denise Patel (`D-44821`, 2024 RAV4, front gross $2,150)
  - a Lakeside Honda warranty claim for Anita Rosales (`WTY-26-04418`, 2019 Accord, transmission cooler line, $1,847.22)
- **A COBOL-style mainframe extract**, `CUSTDEAL.DAT` plus `CUSTDEAL.CPY`: EBCDIC text, packed-decimal amounts (including a -$125.00 chargeback), a `REDEFINES` field, and an `OCCURS 2 TIMES` vehicle group. Two trailing records are deliberately bad so the quality report has something to reject.
- **A messy service-history CSV** with two title rows, inconsistent date formats (`11/3/26`, `18-Mar-2026`, `20260930`), a VIN with spaces, parentheses for a credit, and a row whose amount is `see jacket`.
- **A messy deal-register Excel file** with a title row, awkward headers (` Front Gross$ `), and a mix of Excel serial dates and text dates.
- **A plain memo** from Patricia Walsh, GM of Lakeside Honda, about fuel-pump recall `24V-312`, pointing staff at Anita's paper jacket.

One VIN — Anita's 2019 Accord, `1HGCV2F36KA123456` — shows up in the scan, the mainframe file, the spreadsheet, and the memo, so a single search can cite more than one source.

## How it works

There is **no paid API**.

1. **Detect.** A file is classified as a scan, a copybook, a mainframe data file, CSV, Excel, or plain text, using the suffix and a sniff of the contents (including an EBCDIC-byte score).
2. **Extract.**
   - Scans and scanned PDFs are deskewed and thresholded, then read with Tesseract (`pytesseract`). Low-confidence words are flagged for review.
   - Mainframe files are decoded with the companion copybook: display fields in EBCDIC (CP037), amounts as IBM packed decimal (COMP-3), `REDEFINES` at the same offset, `OCCURS` as a list.
   - CSV and Excel files have their header row found automatically. Column aliases are mapped (`Cust. Name` → customer, `Vin #` → VIN, ` Front Gross$ ` → amount).
   - Text memos are kept as narrative and scanned for VINs, dates, and dollar amounts.
3. **Clean.** Dates become ISO `YYYY-MM-DD` (US `MM/DD/YY` is the default for slashes). Currency becomes a two-decimal dollar figure, including parentheses or a trailing minus for credits. VINs are uppercased and stripped of spaces; the ISO 3779 check digit is validated. `LAST, FIRST` names are flipped and title-cased.
4. **Chunk.** Structured rows stay one chunk each, so a citation points at a single record. Long OCR pages and memos are packed into overlapping windows of about 700 characters.
5. **Index.** Default retrieval is **TF-IDF** (scikit-learn) with cosine similarity — a local sparse embedding, no model download. Chunks and their provenance are stored in a local SQLite file under `data/index/` (that folder is gitignored and rebuilt on ingest).
6. **Quality report.** Counts of parsed and rejected records, rejects with reasons, and low-confidence OCR items for a person to review.

### Optional sentence-transformers (off by default)

If you later install `sentence-transformers` and a small MiniLM model, you can switch the backend without changing the rest of the pipeline:

```bash
pip install sentence-transformers
export LEGACY_INGESTOR_EMBEDDINGS=sbert
streamlit run app.py
```

If that import or model load fails, the app falls back to TF-IDF.

## Honest limitations

- This is a **demo**. Lakeside Auto Group and every customer, VIN, dollar figure, and employee are fictional.
- The copybook parser covers a useful subset of COBOL (`PIC X` / `PIC 9`, `COMP-3`, `REDEFINES`, `OCCURS`), not a full compiler. Real customer copybooks are messier than this one.
- OCR is **Tesseract**, not a paid document API. It will misread a character, especially on a crooked scan. The quality report is supposed to show that, not hide it.
- Default retrieval is **lexical TF-IDF**, not a large embedding model. Paraphrases can miss. That is a tradeoff so the demo runs offline with no model download.
- Normalization is rule-based. Ambiguous dates are treated as US `MM/DD`, which is right for this dealer group and wrong for some others.
- Uploading a real customer export still keeps this a demo app: no SSO, no encryption-at-rest story, no write-back to a DMS, and no audit log shipped to a SIEM.
- Sample forms are **generated to look scanned**. They are not photographs of real deal jackets.

## What a production version would add

- Connectors to the real systems of record — a DMS, a document management system, a mainframe transfer, a shared inbox of scans — with a scheduled or event-driven ingest
- A human review queue for low-confidence OCR and rejected records, with corrections written back into the store
- Better OCR and layout analysis (or a document AI service the customer already has), plus handwriting support
- A fuller copybook / EBCDIC toolchain, including packed and zoned decimals as the customer's layout actually uses them
- Evaluation of extraction quality against a labeled hold-out set, and retrieval quality on a question set
- Deduping, versioning, and legal hold when the same VIN appears in a scan and a later DMS extract
- Encryption at rest, access control, and an audit trail of who searched or exported what
- A hand-off into the rest of the AI stack (a secure RAG index, an approval gate) once the data is clean enough to trust

## Project layout

```
ai-legacy-ingestor/
  app.py                 Streamlit UI
  run.sh                 One-command launcher
  requirements.txt       streamlit, numpy, scikit-learn, pandas, pillow, pytesseract, openpyxl, pypdf
  README.md
  LICENSE                MIT, Copyright (c) 2026 Daniel McBrearty
  DEMO_SCRIPT.md         ~1-minute talk track for interviews
  ingestor/              Detect, extract, normalize, chunk, index, sample generator
  data/samples/          Bundled scans, mainframe extract, CSV, Excel, memo
  examples/              Saved search with citations
  screenshots/           App screenshot (if present)
  tests/                 Copybook, normalization, chunking, provenance, OCR, and search checks
```

## For interviewers

If you only have a minute, start the app on the default search, read the top citation on Anita Rosales's warranty claim, then open **Quality report** and point at the rejected mainframe records. The talk track is in [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md).

Daniel's background is car sales, F&I, and auto software sales (Dealr.cloud), not professional software engineering. This project is meant to show he can talk about **week-one data wrangling** the way a dealer group already talks about paper deal jackets and old DMS exports — and that he is honest about what a demo does not prove.

## License

This project is released under the [MIT License](LICENSE). Copyright (c) 2026 Daniel McBrearty.
