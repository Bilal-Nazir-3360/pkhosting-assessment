# NOTES
This file covers Part A (the renewals cleanup). The notes and findings for Part B
(the TECHi reader) are in README.md.

## About the data

The file `renewals_raw.csv` was not included with my assessment. I checked the
email, the spam folder and the assessment page, and I asked the team about it.
So I made `renewals_sample.csv` (50 rows) myself. It copies the problems in the
brief and adds a few more. All numbers below come from this sample. When the
real file arrives I will run `python clean.py renewals_raw.csv`, update the
numbers, and check each rule again.

## Ambiguous dates

The file mixes DD/MM/YYYY and MM/DD/YYYY, so I decide the order per row, not
once for the whole file.

1. If one part is bigger than 12, it can only be a day. The order is certain.
2. If both parts are 12 or less, I use two checks:
   - the other date in the same row (I assume both dates in a row use the
     same format)
   - whether registered_on + billing cycle equals renews_on under each reading
3. If both readings still fit, I use day-first (Pakistan's usual style), keep
   the row, and log it in issues.csv as "ambiguous_date".
4. If neither reading is a real date (for example 31/02/2025), the date is left
   blank, the row is flagged, and it is not counted in the total.

Formats like 2025-08-10, 2025/09/01 and 03-Aug-2025 have only one possible
reading, so they are never ambiguous.

Two-digit years are read as 20xx, because all PKHosting records are from the
2000s. Any year outside 2000 to 2035 is flagged as "implausible_year".

In my sample, four rows stay guessed: R004, R006, R017 and R040.

## Money

- No currency sign means PKR. "USD" or "$" means USD, and I do not convert it.
- Brackets mean a refund (negative). A leading minus means a negative amount.
- One "," or "." followed by exactly 3 digits is a thousands separator, because
  PKR is whole rupees. So "1,200" and "1.200" both mean 1200.
- If both "," and "." appear, the last one is the decimal ("1.200,00" is 1200).
- Whole rupees are written without ".0" (3500, not 3500.0).

## Domains

I make the domain lowercase and remove http(s)://, www., the path, the port and
trailing dots. Subdomains are kept. Non-English letters become punycode
(Café.pk becomes xn--caf-dma.pk), because that is the form DNS uses. A domain
with an empty part (shop..com.pk) is invalid, and that row is dropped.

## Other rules

**Status.** Allowed values: active, cancelled, suspended, expired, pending,
refunded, unknown. "canceled" becomes "cancelled". A blank or unknown value
becomes "unknown" and is flagged.

**Billing cycle.** Stored as whole months. 12, "1 year" and "Annual" are 12.
"6 months", "half year" and "semi-annual" are 6. "Quarterly" is 3. "Monthly"
is 1. A blank cycle is worked out from the two dates and flagged. If the cycle
does not match the dates (R024), I flag it and do not change it. Anything else
is flagged as unrecognised.

**Dropped and flagged.** Dropped means the row is not in clean.csv. Flagged
means the row is in clean.csv and has at least one line in issues.csv.

**Duplicates.** Two rows are the same renewal if they have the same domain,
service and renewal date. If the amounts are the same, I keep the first row and
drop the later one. If the amounts are different (R009 and R010), I keep the
first row, flag it as "conflicting_duplicate", log both amounts, and leave it
out of the headline total. I cannot tell which amount is right.

**Reused record_id.** R004 is used by two different renewals. I keep both and
flag both. I did not merge them.

**Sanity checks (flag only, never change the data):**
- renewal date not after registered date (R015)
- zero amount, or negative amount on a row that is not a refund
- amount above Rs. 1,000,000 (my own limit, because I have no real data to set it)
- status is "active" but the renewal date is before 2026-08-03
- one customer with several contact emails (C101)

**What is not logged row by row.** Changing dates to ISO format, and removing
"Rs.", commas and "/-" from amounts. This happens on almost every row, so
logging it would bury the real problems. Changes to domain, status, service,
cycle and email are logged.

**About issues.csv.** It has one row per problem, not one row per record, so a
record with three problems appears three times.

## Renewal total: 2026-08-03 to 2026-09-02

Today is 2026-08-03. Both end dates are included.

- **Headline total: Rs. 183,100** (21 renewals with certain dates).
- With the two rows whose dates were guessed (R017 and R040): **Rs. 191,600**.
  The guess changes the total by Rs. 8,500, so I show both.

The row-by-row list with a reason for each row is in `renewal_report.csv`.

**Counted:** active and pending rows with a PKR amount. I count pending because
it is a normal renewal that has not been paid yet.

**Not counted, and why:**
- Cancelled (R012, R013): they will not renew.
- Unknown status (R044): I cannot trust the status.
- Zero or negative amount (R025, R026): not a real renewal payment.
- USD line (R046): no exchange rate was given, and I did not invent one.
- Outlier (R027, Rs. 3,500,000): probably a data error. Listed separately to check.
- Conflicting duplicate (R009 and R010): Rs. 24,000 or Rs. 26,000. I cannot tell
  which is right, so neither is in the headline. If someone confirms the amount,
  the total goes up by that amount.
- Rows whose renewal date could not be read (R005, R050): they cannot be placed in
  the window, so they are excluded and listed in renewal_report.csv.

**Shown separately:** suspended R014 (Rs. 30,000) is "at risk". It may come
back, but I do not treat it as expected money.

**Refunds.** A refund is money going out, not a renewal due, so I would never
count it. In my sample the refund (R006) and the blank amount (R007) renew
outside this window, so they do not change the total.

**Counted, but flagged:** R024 (cycle says 12 months, dates are 6 months apart)
and R049 (customer has a second contact email). The amounts look normal, so I
kept them in the total.