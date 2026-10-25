# Democracydot

Democracydot is an AI-supported civic technology project designed to make the legislative process more transparent, understandable, and engaging for the public. The goal is to turn dense policy and legal language into a clearer, more accessible understanding of what a Bill means, why it matters, and how it changes during parliamentary review.

## Project record

The repository has progressed from its initial Python/Streamlit scaffold to a working three-stage prototype for following legislative proposals and constituent engagement. Completed work includes:

- Established the project mission and Python development setup
- Copied and moved the code to the Democracydot.com repository to access more credits and continue development
- Added a Streamlit application with a sidebar flow across Bill Information, Democratic Engagement, and Democracy Index
- Added a responsive visual design system using cornflower blue, marine navy, white, and neon-pink accents
- Integrated OpenAI using `gpt-4o-mini` for plain-language Bill summaries, source-grounded questions and answers, and structured Bill-version comparisons
- Added upload and text extraction for PDF, plain-text, and Markdown policy and information documents
- Added a Billbow comment form and a configurable list of essential-reading links
- Added a free, no-password sign-up form that collects mobile and email with required permission for updates and announcements
- Added a visual Demodot Meter and an AI-estimated Democracy Index for original/final Bill alignment
- Removed the Act as passed PDF button while retaining the embedded document and comparison feature
- Added durable Billbow comment and opted-in contact storage, visible only through the password-protected owner review page
- Added API credential loading from a local `.env` file or Streamlit secrets, and ignored local secrets and Python bytecode in Git
- Updated this documentation with setup, behavior, security/privacy notes, limitations, and the original feature instructions
- Reordered the pages to Bill Information, Democratic Engagement, and Democracy Index, with matching titles in the sidebar and on the landing page
- Added a link to Madeleine Ogilvie MP's Facebook page on the landing page, and gated the Democracy Index download behind a self-declared follow of that page (the declaration is not verified by Facebook)
- Added an on-screen view of the compared document, and search that starts when a Bill name is entered
- Added a Privacy Policy page (`/privacy`) and Terms and Conditions page (`/terms`), with a browse-to-accept notice on every page
- Merged the Guided Bill Analysis into the Bill Information page (checkbox list of analyses and a pink **Compile a Report** button), made the Proposed amendment generate when Enter is pressed, and updated the Facebook, LinkedIn and footer links on the landing page
- Removed the OpenAI data-sharing and Essential reading captions from the top of Bill Information
- A device that has already given its name and mobile number is now recognised on every page (not only Bill Information), so the Download documents button unlocks without re-entering them
- Added optional Postgres storage through a `DATABASE_URL` secret (any hosted Postgres provider; none chosen yet) so sign-ups and comments can survive Streamlit Cloud restarts; local development still uses SQLite
- Added a pink **Download documents** button above the Billbow heading on Democratic Engagement that bundles the official Bill PDFs shown on the page into one ZIP (enabled once the name and mobile form has been completed)
- On the Democracy Index page, a Bill carried over automatically from page 1 now also runs **Create Democracy Index** as soon as the Parliament search finds it
- Changed "Download Bill information" to a pink "Download full report": a formatted HTML document combining the Bill information, essential reading, guided analysis, Hansard summary and public discussion
- Added a pink formatted HTML "Download summary" button under the public discussion summary (same Facebook tick and name/mobile unlock)
- Added a formatted HTML "Download Summary" button under the Hansard AI summary (enabled after the Facebook tick and name/mobile form)
- The name and mobile number form is skipped on a device that has already submitted it (remembered with a browser cookie linked to the stored sign-up)
- Added a name and mobile number form (stored in the signups table) that must be completed before the Bill information download unlocks
- Moved the Bill Information download section under the "AI supported" line, removed its heading and the "enter a Bill name" box, and reworded the pink button and honour-system note ("It's an honour system")
- Changed the Guided Bill Analysis download from raw Markdown to a formatted HTML report that matches the on-page layout
- Set the left-hand navigation sidebar to open expanded so each page opens with a single click
- Fixed the HTTP 403 on Bill lookup from the hosted app: requests retry with alternate headers, Bills are found from the Parliament Bills lists before the site search, and 403 errors name the refused address
- Added a saved snapshot of 2025-2026 Bill records, status and PDFs (`snapshot/`, built by `build_snapshot.py`). The app tries the live Parliament site first and falls back to the snapshot when Parliament's bot protection (Cloudflare) refuses the hosting provider
- Fixed the **Act as passed** section on Democracy Index so the Act comes up automatically: Acts passed in a later year than the Bill (the legislation site names an Act by the year it was passed) and Appropriation/Supply Bills with "(No. n)" or "(Bill n of year)" in the title are now found, and the section explains when a Bill has no Act yet
- The "saved Parliament records are being used" notice now shows once per page load instead of repeating when several lookups fall back to the snapshot
- Removed the "Explore the Bill, share your perspective…" line from the home page

## Vision

Democracydot is intended to help users:

- Understand legislative proposals in plain language
- Compare proposed laws and amendments
- See likely impacts across communities and institutions
- Identify stakeholders, trade-offs, and policy implications
- Explore civic issues with AI-guided analysis rather than raw legal text alone

The longer-term aim is to support more informed public engagement around lawmaking by combining AI analysis with accessible presentation of policy information.

## Technology stack

The project is currently grounded in a lightweight Python stack designed for experimentation and rapid iteration:

- Python
- Streamlit for an interactive user interface
- OpenAI models for policy analysis and summarization
- python-dotenv for environment management

## Current implementation status

The Streamlit application opens on a public landing page, and all three Bill features are available without signing in or registering. Navigation is configured in `app.py` (the left-hand sidebar starts expanded, so each page opens with one click), with each page implemented as a dedicated Streamlit page: the home page, Bill Information, Democratic Engagement, and Democracy Index.

1. **Bill Information** — enter a Bill title and press Enter to retrieve the Bill from Tasmanian Parliament records and draft any empty summary, background, and policy context fields (existing text is kept, and the draft should be reviewed); or enter them yourself. The **Guided Bill Analysis** section on this page can run five focused analyses (summary, key changes, affected groups, risks and concerns, and a plain-English explanation) from the official Bill or an uploaded PDF/text file, compile them with an AI-written conclusion, and download the report as a formatted HTML document with a pink **Download analysis report** button that matches how it appears on the page (open it in a browser or print it to PDF). Essential reading shows the Bill's full official title and number, with Hansard debate links and links to any House of Assembly or Legislative Council e-petitions on the Bill or its subject matter added automatically, you can create a Hansard AI summary of the debates (House of Assembly, then Legislative Council, then a conclusion) and download it as a formatted HTML document with the pink **Download Summary** button (unlocked by the same Facebook tick and name/mobile form), download the public discussion summary the same way with the pink **Download summary** button, and, at the bottom of the page, download a **full report**: a formatted HTML document combining the Bill information, Essential reading, Guided Bill Analysis, Hansard AI summary and public discussion that have been generated. The download section sits directly under the "This function is AI supported" line, with a pink "Please follow me on facebook for downloads access" button, the note "It's an honour system", and an "I follow Madeleine Ogilvie MP on Facebook" tick box (self-confirmed, not verified). Below it, a form asks for a name and mobile number (skipped on a device that has already submitted it); pressing the pink **Continue** button validates the details and stores them in the local SQLite signups table, remembers the browser with a one-year cookie so the form is not shown again on that device, (the same one shown to the owner on the Owner review page). The pink **Download full report** button then appears at the bottom of the page, above the Parliament website link.
2. **Democratic Engagement** — the Bill entered on page 1 is carried over and searched automatically (or type another Bill name and press Enter to search Tasmanian Parliament records). The matching Bill as introduced PDF, second reading speech, fact sheet, and clause notes are retrieved and displayed. The page reports the official House of Assembly, Legislative Council, and Royal Assent status, and links to the Final Act when available. Users can ask AI-grounded questions, request an AI-drafted proposed amendment using the available Bill or Act text, and submit anonymous feedback. A pink **Download documents** button above the Billbow heading downloads the Bill and other official PDFs shown on the page as one ZIP file, once the name and mobile number have been entered on Bill Information (a device that has already submitted them is recognised on every page).
3. **Democracy Index** — the Bill entered on page 1 is carried over and searched automatically for the session (you can still search another Bill). enter a Bill name on the Tasmanian Parliament website search to view its introduced PDF and automatically find and view the corresponding Act as passed PDF. The search starts when the name is entered, and when the Bill is carried over automatically from page 1 the Democracy Index is created automatically once the Bill is found (typing a different Bill still needs the **Create Democracy Index** button). Under the **Generate Democracy Index** heading, use the **Create Democracy Index** button (with a countdown timer while it processes) to get an AI-assisted alignment score. The separate **Generate compare document** button builds the compared document with changes marked, shows it on screen and offers it for download with a pink **Download compare document** button. The report also shows a "Democratic importance" weighting from the signatures on related House of Assembly and Legislative Council e-petitions (limited, moderate, high or very high; paper petitions are not counted). The finished Democracy Index report can be downloaded with the pink **Download the Democracy Index** button (including the Democracy Index graphic and a Democracydot terms notation), with no confirmation tick box.

The **Privacy Policy** (`/privacy`) and **Terms and Conditions** (`/terms`) are also available as pages, and a notice at the bottom of every page says that using the app means accepting the terms.

The OpenAI features use `gpt-4o-mini`. The Democracy Index is an AI-assisted estimate based only on the supplied Bill texts; it is not an official parliamentary rating, a measure of democratic legitimacy, or legal advice.

## Development setup

Create and activate the virtual environment, then install the project dependencies:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Enter your OpenAI API key in the **sidebar** ("OpenAI API key") when using the app; it is kept only in the session. Alternatively, put it in the root `.env` file or Streamlit secrets as a fallback:

```env
OPENAI_API_KEY=your_api_key_here
```

Never commit or share your key. Text and documents are sent to OpenAI only when an AI feature is requested. Do not upload personal or sensitive information without permission.

To enable the private owner review page, set a strong password in the root `.env` file:

```env
DEMOCRACYDOT_OWNER_PASSWORD=choose-a-strong-unique-password
```

For deployment, configure `DEMOCRACYDOT_OWNER_PASSWORD` in Streamlit secrets instead. Billbow comments and sign-up names and mobile numbers are stored in `comments.sqlite3` in the project root when running locally. On Streamlit Community Cloud that file is lost whenever the app restarts, so sign-ups and comments will not last until a durable database is chosen. The app already supports any hosted Postgres database: set a `DATABASE_URL` secret and it is used automatically, with no other code change. No provider has been chosen yet.

To use a hosted Postgres database, copy its **connection string** (it looks like `postgresql://user:password@host/dbname?sslmode=require`) and add it to the app's Streamlit secrets. Keep the string private; never commit it.

```toml
OPENAI_API_KEY = "sk-..."
DEMOCRACYDOT_OWNER_PASSWORD = "choose-a-strong-password"
DATABASE_URL = "postgresql://user:password@host/dbname?sslmode=require"
```

The tables are created automatically the first time the app saves or reads data.

## Deployment

The app is deployed from this repository on Streamlit Community Cloud (repository `mrogilvie/Democracydot.com`, branch `main`, main file `app.py`). Add `OPENAI_API_KEY` and `DEMOCRACYDOT_OWNER_PASSWORD` under **Advanced settings → Secrets**. Pushes to `main` update the live app. Community Cloud does not support custom domains, so the app is served from a `streamlit.app` address.

### Public repository

Streamlit Community Cloud allows only one private app per account, so this repository is made public. The code is safe to publish because it is a civic app with nothing sensitive in the source. Private data, such as sign-ups, comments, the OpenAI key, the owner password and any database connection string, stays out of the repository: keep secrets only in Streamlit **Secrets**, and never commit them.

## Run the app

After completing the development setup, start the Streamlit app from the repository root:

```sh
streamlit run app.py
```

Streamlit prints a local URL in the terminal. Open that URL in a browser to use the app and move between pages in the sidebar; no sign-in is required. Bill details and links are retained in the session, while comments and sign-ups are stored in the local SQLite database.

## Repository layout

```text
app.py                      Streamlit page configuration and navigation
design_system.py            Shared Democracydot colors, typography, and component styles
demodot.py                  Shared OpenAI, source-text, and Bill-session helpers
comment_store.py            SQLite (local) or Postgres (DATABASE_URL) storage for Billbow submissions and sign-ups
bill_snapshot.py            Reads the saved Parliament Bill records in snapshot/
build_snapshot.py           Rebuilds snapshot/ (Bill records, status and PDFs) from the live Parliament site
snapshot/                   Saved 2025-2026 Bill records and PDFs used when the live site refuses the app
pages/
  home.py                   App overview and links into the three stages
  bill_interaction.py       Page 1, Bill Information: details, links, and optional summary
  decision_phase.py         Page 2, Democratic Engagement: Billbow comments and Bill-grounded Q&A
  bill_information.py       Page 3, Democracy Index: Bill comparison, markup, and Demodot Meter
  privacy.py                Privacy Policy page, rendered from PRIVACY.md
  terms.py                  Terms and Conditions page, rendered from TERMS.md
  owner_review.py           Password-protected review of comments and sign-ups
PRIVACY.md                  Privacy Policy text
TERMS.md                    Terms and Conditions text
requirements.txt            Python dependencies
```

## Saved Bill snapshot

The Parliament of Tasmania website is behind Cloudflare bot protection, which can answer HTTP 403 to requests from cloud hosts such as Streamlit Community Cloud even though the same requests work from a browser. To keep Bill lookups working, the repository holds a snapshot of the Bills introduced in 2025 and 2026 in `snapshot/` (an `index.json` of Bill titles, document links, passage status and Act links, plus the PDFs in `snapshot/pdfs/`).

The app always tries the live site first. If Parliament refuses the request, it uses the snapshot for Bill matching, document links, status and PDFs, and shows a note with the snapshot date. After a refusal it skips live requests for five minutes so pages stay quick. Bills outside the snapshot still need the live site. Hansard, e-petition and AI web-search features are not part of the snapshot.

The snapshot goes out of date as Bills progress or new ones are introduced. Refresh it from a machine where Parliament is reachable (for example the Codespace), then commit `snapshot/`:

```sh
python build_snapshot.py          # 2025 and 2026
python build_snapshot.py 2026     # chosen years only
```

## Dependency list

The current dependency set is defined in `requirements.txt` and includes:

- openai
- streamlit
- markdown
- python-dotenv
- pypdf

## Original feature instructions

The following is the user's original feature request, preserved verbatim as a product reference:

> This app will simplify constituents engagement with the legislative drafting and parliamentary debate process. It has three sub processes. Each sub process will have its own page on Streamlit. The app will help residents comprehend and participate in the legislative process. It will also allow them to share their views on the Bill and allow the app owner to review those comments.

## Planned roadmap

1. Add moderation and retention controls for owner-reviewed Billbow submissions
2. Retrieve and cite official Bill texts and Hansard records
3. Improve AI analysis with source citations and traceable evidence
4. Add durable Bill records and support comparisons across Bills or policy areas
