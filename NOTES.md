## Ambiguous dates

The file mixes DD/MM/YYYY and MM/DD/YYYY, so I decide the date order per row,
not once for the whole file.

1. If either part of a date is greater than 12, it can only be a day, so the
   order is certain.
2. If both parts are 12 or less, I use two checks:
   (a) the other date in the same row, assuming both dates in a row share one
       format;
   (b) whether registered_on + billing_cycle_months equals renews_on under each
       reading.
3. If both readings still fit, I default to day-first (Pakistan's convention),keep the row, and log it in issues.csv with the problem "ambiguous_date".
4. If neither reading is a real calendar date (e.g. 31/02/2025), the date is left blank, the row is flagged, and it is excluded from the renewal total.

The renewal total is reported twice, with and without the ambiguous_date rows,so the effect of the guess is visible.

Two-digit years are read as 20xx, because all records are from the 2000s.

Two-digit years are read as 20xx, because PKHosting records are all from the 2000s. Any parsed year outside 2000 to 2035 is flagged as implausible_year in issues.csv, not silently accepted.


## Money --------

- if there is no currency means PKR. if "USD" or "$" means USD, and the amount is not converted.
- Parentheses mean a refund (negative). A leading minus means a negative amount.
- if a single "," or "." followed by exactly 3 digits is a thousands separator
  (PKR is whole rupees), so "1,200" and "1.200" both mean 1200.
- If both appear, the last one is the decimal separator ("1.200,00" = 1200.00).