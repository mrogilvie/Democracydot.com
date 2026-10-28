# Test Case Documentation

## Run summary

- **Run date:** 28 October 2026 (UTC)
- **Checks performed:** Parliament Bill lookup, introduced Bill document retrieval and PDF text extraction; Bill-status retrieval where relevant; Residential Parks Act lookup and PDF text extraction.
- **Result:** Two test cases passed. The Conversion Practices Bill lookup, introduced Bill PDF, and parliamentary status checks passed, but the Hansard check was inconclusive because requests timed out for both chambers, including on retry.
- **AI features:** Not run. These cases verify official-record retrieval and document handling and do not require an OpenAI API key.
- **Source handling:** PDFs were downloaded and checked during the run, but are not redistributed here. The JSON results record official source URLs, page counts, extracted-text lengths, byte counts, and SHA-256 digests.

The run used the app's Parliament lookup and document retrieval functions, with the configured repository snapshot fallback available for functions that support it. Results describe the records returned during this run and may change as Parliament records are updated.

## Test cases

| Test case | Result | Main output |
|---|---|---|
| [Conversion Practices Prohibition Bill 2026 (45 of 2026)](./01-conversion-practices-prohibition/results.json) | **Partial** — Bill lookup, PDF, and status passed; Hansard timed out twice. | [Official Bill PDF](https://www.parliament.tas.gov.au/__data/assets/pdf_file/0021/111288/45-of-2026.pdf) |
| [Residential Parks Bill 2026 (Act 13 of 2026)](./02-residential-parks-act-13-2026/results.json) | **Passed** — resolved to Parliament record 2 of 2026; introduced Bill, status, and Act as passed retrieved. | [Official Bill PDF](https://www.parliament.tas.gov.au/__data/assets/pdf_file/0023/102488/2-of-2026.pdf) · [Residential Parks Act 2026, No. 13](https://www.legislation.tas.gov.au/view/pdf/asmade/act-2026-013) |
| [Electoral Disclosure and Funding Amendment (Spending Limits) Bill 2026 (49 of 2026)](./03-electoral-disclosure-spending-limits/results.json) | **Passed** — Bill record and introduced Bill PDF retrieved and text-extracted. | [Official Bill PDF](https://www.parliament.tas.gov.au/__data/assets/pdf_file/0023/113747/49-of-2026.pdf) |

The [consolidated machine-readable run results](./run-results.json) contain the detailed outputs for all three cases.
