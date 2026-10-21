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

The Streamlit application opens on a public landing page, and all three Bill features are available without signing in or registering. Navigation is configured in `app.py`, with each page implemented as a dedicated Streamlit page: the home page, Bill Information, Democratic Engagement, and Democracy Index.

1. **Bill Information** — enter a Bill title and press Enter to retrieve the Bill from Tasmanian Parliament records and draft any empty summary, background, and policy context fields (existing text is kept, and the draft should be reviewed); or enter them yourself. Essential reading shows the Bill's full official title and number, with Hansard debate links added automatically, and you can create a Hansard AI summary of the debates (House of Assembly, then Legislative Council, then a conclusion).
2. **Democratic Engagement** — enter a Bill name to search Tasmanian Parliament records. The matching Bill as introduced PDF, second reading speech, fact sheet, and clause notes are retrieved and displayed. Then the user can ask AI-grounded questions using the material on the Bill Information page and submit anonymous feedback.
3. **Democracy Index** — enter a Bill name on the Tasmanian Parliament website search to view its introduced PDF and automatically find and view the corresponding Act as passed PDF. The search starts when the name is entered. Use the **Compare document** button to see the compared document on screen with changes marked, and to get an AI-assisted alignment score. Downloading the marked-up comparison requires the user to confirm they follow Madeleine Ogilvie MP on Facebook; this is a self-declaration and is not verified.

The **Privacy Policy** (`/privacy`) and **Terms and Conditions** (`/terms`) are also available as pages, and a notice at the bottom of every page says that using the app means accepting the terms.

The OpenAI features use `gpt-4o-mini`. The Democracy Index is an AI-assisted estimate based only on the supplied Bill texts; it is not an official parliamentary rating, a measure of democratic legitimacy, or legal advice.

## Development setup

Create and activate the virtual environment, then install the project dependencies:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

To enable AI summaries, Bill Q&A, and version comparison, put your OpenAI API key in the root `.env` file:

```env
OPENAI_API_KEY=your_api_key_here
```

The app also supports an `OPENAI_API_KEY` value in Streamlit secrets when deployed. Never commit or share your key. Text and documents are sent to OpenAI only when an AI feature is requested. Do not upload personal or sensitive information without permission.

To enable the private owner review page, set a strong password in the root `.env` file:

```env
DEMOCRACYDOT_OWNER_PASSWORD=choose-a-strong-unique-password
```

For deployment, configure `DEMOCRACYDOT_OWNER_PASSWORD` in Streamlit secrets instead. Billbow comments and any previously collected opted-in sign-up names and mobile numbers are stored in `comments.sqlite3` in the project root. On Streamlit Community Cloud these files are lost when the app restarts, so durable storage there needs an external database.

## Deployment

The app is deployed from this repository on Streamlit Community Cloud (repository `mrogilvie/Democracydot.com`, branch `main`, main file `app.py`). Add `OPENAI_API_KEY` and `DEMOCRACYDOT_OWNER_PASSWORD` under **Advanced settings → Secrets**. Pushes to `main` update the live app. Community Cloud does not support custom domains, so the app is served from a `streamlit.app` address.

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
comment_store.py            SQLite persistence for anonymous Billbow submissions
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

## Dependency list

The current dependency set is defined in `requirements.txt` and includes:

- openai
- streamlit
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
