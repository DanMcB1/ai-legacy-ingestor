# Demo script (~1 minute)

A talk track you can say out loud in an interview. Plain language. Practice it once with the app open on the default search. You do not need to memorize it word for word.

**Setup:** `streamlit run app.py` is already running. Leave the search on the default Anita Rosales warranty-claim query. You will point at the top citation, then at the quality report.

---

## The talk track

“Every dealer group I’ve walked into still has a filing cabinet of paper deal jackets, and at least one export from an old DMS that nobody wants to open. Week one of an AI project is almost never ‘pick a model.’ It’s ‘can we even read the data?’

This is a demo that takes four messy sources — a crooked scan of a 1990s-style warranty claim, a mainframe file that’s still in EBCDIC with packed-decimal amounts, a spreadsheet with three different date formats, and a GM memo — and turns them into a searchable store. Every answer cites the source file, and the page or the record number, so you can go back to the paper.

I’m searching for Anita Rosales’s warranty claim on a transmission cooler line. The top hit is the scanned form: claim WTY-26-04418, her VIN, the dollar total, and an OCR confidence. The next hits are the GM’s memo about a fuel-pump recall, which mentions the same jacket, and a row from the deal register. Same customer, three sources, each with a citation.

And I want to be honest: this is a demo, not a production migration tool. The files are sample data for a fictional Lakeside Auto Group. OCR will misread a character now and then — that’s why there’s a quality report, with rejected mainframe records and a couple of low-confidence words flagged for a person to review. I would rather show that on week one than pretend the data was clean.”

---

## Timing notes

Spoken at a normal pace, that is about 50–60 seconds. If you have a few extra seconds, open **Quality report** and point at the two rejected `CUSTDEAL.DAT` records — a smashed packed-decimal amount and a truncated row — and say: “That’s the conversation I want on day one: what parsed, and what still needs a person.” Then stop and let them ask questions.

## If they ask a follow-up

- **“What’s actually in the mainframe file?”**  
  “It’s a fixed-width extract with a COBOL copybook. Names and VINs are EBCDIC. The dollar amounts are COMP-3, packed decimal, including a negative chargeback. There’s a `REDEFINES` and an `OCCURS` group for vehicles. I wrote a small parser for that subset — it’s not a full COBOL compiler.”

- **“Why not just use ChatGPT or a document AI API?”**  
  “You can, in production, if the customer already has one and the files are allowed to leave the building. I didn’t want the demo to depend on a key, or to hide the wrangling behind a black box. The valuable part here is the pipeline and the provenance, not a particular OCR vendor.”

- **“Is the search using embeddings?”**  
  “The default is TF-IDF and cosine similarity on this machine, so it runs offline with no model download. If you install a small local sentence-transformers model, the same chunks and citations still apply.”

- **“What would you do with a real dealer group’s files?”**  
  “Start with a week-one sample: a box of jackets, one DMS extract, one messy spreadsheet. Run them through a pipeline like this, sit with the office manager and the controller on the rejects, and only then talk about what an assistant is allowed to answer. I would not train or retrieve over data I couldn’t cite.”

- **“What would production look like?”**  
  “Connectors into the DMS and the document system, a review queue for low-confidence OCR, a fuller copybook toolchain, access control, and a hand-off into the rest of the stack — a secure search index, an approval gate — once the quality report is something finance will live with.”
