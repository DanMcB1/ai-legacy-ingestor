# Example: search for Anita Rosales's warranty claim

This is a saved copy of a search against the bundled Lakeside Auto Group (sample) files, after `python -m ingestor ingest`. It is sample data. The command was:

```bash
python -m ingestor search "warranty claim transmission cooler line Anita Rosales"
```

Typical top hits (wording may shift slightly if you re-run OCR, but the sources should stay the same):

1. **warranty-claim-lakeside-honda.png, page 1, OCR ~93%**  
   The scanned warranty claim: claim `WTY-26-04418`, VIN `1HGCV2F36KA123456`, 2019 Honda Accord, transmission cooler line, claim total `$1,847.22`.

2. **gm-recall-memo.txt, record 1, lines around the Anita paragraph**  
   Patricia Walsh's memo on fuel-pump recall `24V-312`, which tells the store to pull Anita's paper jacket for the same claim.

3. **deal-register-export.xlsx or CUSTDEAL.DAT**  
   The same VIN on a deal-register row or the mainframe extract of her 2019 Accord deal.

That is the point of provenance: one customer, more than one messy source, each hit pointing back to a file, a page, or a record number.
