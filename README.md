# MOSAIC Learn - Streamlit prototype v4

This version aligns the prototype much more closely with the MOSAIC visual identity and changes the information architecture so that **Convince behaves differently from the learning journey**.

## The key design decision

The MOSAIC Learn source material defines three levels:

- **Understand** - key concepts, evidence and terminology.
- **Apply** - use the knowledge in policy, research or practice.
- **Convince** - arguments, examples and resources that help communicate the topic and inspire action.

In v4, **Understand + Apply are the tracked course experience**. **Convince is a separate evidence and communications hub**. It does not count toward course completion and it does not use the theory-slider lesson pattern.

This makes Convince a better home for:

- MOSAIC examples and short case stories;
- audience-specific arguments;
- policy briefs;
- pitch decks;
- impact/evidence sheets;
- source deliverables;
- a reusable 30-second case or talking point.

The Policy Lab **Main Message** remains part of Apply because it is one of the six practical Policy Lab building blocks. The separate Convince hub is for communicating and advocating for the overall method.

## MOSAIC branding applied

The interface now uses the official palette from the MOSAIC Communications Toolkit:

- Grey `#3c3c3b`
- Blue `#0d4f9e`
- Cyan `#88cdd3`
- Green `#156950`
- Lime `#a2ab20`
- Ochre `#bc8a27`
- Wine `#9c2438`

The app uses **Poppins** when it can load from Google Fonts, matching the Toolkit's recommended open-source fallback when Sofia Pro is unavailable. The Streamlit theme also uses MOSAIC wine as the primary interaction colour.

The interface uses soft irregular colour blocks as a MOSAIC-inspired layout motif. These are interface graphics, not a replacement for the official project logo.

### Official logo

The Communications Toolkit says the logo should be implemented from approved source files, so the prototype does not crop a logo out of the PDF. Put the approved full-colour logo at:

`assets/mosaic-logo.png`

The sidebar will automatically use it. See `assets/README.md`.

## Content structure in this draft

### Drivers of Change

Tracked learning:

1. Understand - Land-use change as a system
2. Understand - Which drivers matter for whom?
3. Apply - From high-level targets to local decisions

Separate Convince hub:

- Why analyse drivers?
- MOSAIC examples from Belgium, Portugal, Denmark and Switzerland
- Different arguments for policy advocacy, policy workers, practitioners and academics
- Policy brief / pitch deck / evidence sheet / D3.1 slots

### Policy Labs for Land-Use Change

Tracked learning:

1. Understand - What a Policy Lab is and is not
2. Apply - Focus
3. Apply - Core Group
4. Apply - Policy Mapping
5. Apply - Stakeholder Involvement
6. Apply - Coherent Workplan
7. Apply - Main Message

Separate Convince hub:

- Why use a Policy Lab?
- MOSAIC practice examples
- Audience-specific arguments
- Policy brief / pitch deck / impact and evidence sheet / D2.1 slots

The Policy Lab content is condensed from the existing MOSAIC Learn Coda pages rather than copied wholesale.

## Run locally on Windows PowerShell

From the folder containing `streamlit_app.py`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m streamlit run streamlit_app.py
```

If Streamlit is installed for your Windows user account rather than in the virtual environment:

```powershell
py -m streamlit run streamlit_app.py
```

## Updating an existing deployment

For v4, replace or commit:

- `streamlit_app.py`
- `content.py`
- `db.py`
- `.streamlit/config.toml`
- optionally `assets/mosaic-logo.png` once you have the approved logo asset

No destructive database migration is required. Existing learning progress remains usable. The old Drivers `Convince` lesson is left in the content model for backward compatibility but is excluded from the tracked path and redirects to the new Convince hub.

## Resource links are intentionally not invented

The current Coda Convince pages mention a policy brief, pitch deck and impact/evidence sheet, but the final public file URLs were not supplied in this task. The prototype therefore shows branded resource cards with a clear **connect existing MOSAIC PDF** status instead of creating broken or guessed download links.

Once the public files are ready, add their URLs or bundle the approved files and replace those placeholders.

## Production note

The prototype still uses local SQLite. Before opening accounts, shared results or the Community feature to real external users, move users, progress, posts and share records to persistent managed storage such as Postgres/Supabase.
