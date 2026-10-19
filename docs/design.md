# Interface design

The selected direction uses electric violet, acid lime and Inter. The interface is a local evidence tool: expressive type establishes the hierarchy, while warnings, findings and hashes remain readable and explicit.

The visual references are [Source](design/source-concept.png) and [Results](design/results-concept.png). Current browser captures are [desktop source](screenshots/source-desktop.png), [mobile source](screenshots/source-mobile.png), [desktop findings](screenshots/problems-desktop.png), [mobile findings](screenshots/problems-mobile.png), [filtered evidence](screenshots/filtered-evidence-desktop.png), [correct sample desktop](screenshots/correct-desktop.png) and [correct sample mobile](screenshots/correct-mobile.png).

## Design system

| Role | Choice |
| --- | --- |
| Page canvas | Near black, `#101015` |
| Task and evidence surfaces | Dark violet, `#1D182B` and `#191422` |
| Main text | Off white, `#F5F3FF` |
| Supporting text | Muted lavender, approximately `#AAA5B8` |
| Expressive accent | Electric violet, `#8B5CF6` |
| Primary actions and matched evidence | Acid lime, `#D4FF3F` |
| Coverage warnings | Amber, `#F5B453`, on dark amber |
| Missing or mismatched content | Coral red, `#FF858D` |
| Type | Inter Variable, weights 400–870; monospace for hashes |
| Containers | Open rails and summaries; one source form panel, flat findings table and evidence inspector |
| Controls | Clearly labeled native inputs, 46–58 px actions, visible keyboard focus |

The source screen places a large three-line heading beside the folder form. The lower band explains the check and offers the deterministic sample workflow. Destination and scan setup extend the same type, field, button and surface system. Results retain a numbered flow, prominent coverage warning, open summary strip, searchable findings table and selected evidence inspector. Mobile uses a single column, a two-by-two summary and a horizontally scrollable findings table.

The exact primary headings remain `Start with your Takeout.` and `Your migration, checked.`. Existing source selection, server connection, mode, consent, cancellation, resume, filtering and export action names are preserved. There are no confidence scores or claims that originals can be deleted.

## Local font and license

The application bundles Inter WOFF2 files from `@fontsource-variable/inter` version 5.3.0. The package contains variable weights 100–900 and separate Latin, extended Latin, Cyrillic, extended Cyrillic, Greek, extended Greek and Vietnamese subsets. The browser requests the relevant subsets from the local application; it does not contact a font service.

Inter is copyright The Inter Project Authors and is distributed under the SIL Open Font License 1.1. The upstream license is available in [the Inter repository](https://github.com/rsms/inter/blob/master/LICENSE.txt). An unmodified copy is retained at `frontend/public/INTER-LICENSE.txt` and is copied into `pmc/web/INTER-LICENSE.txt` with each build. Font binaries are bundled into `pmc/web/assets/`.

## Browser and visual checks

The production build was checked with Playwright Chromium because the Browser plugin was unavailable. Desktop captures use a 1505 × 1045 viewport; mobile captures use 390 × 844. The source and result captures were inspected beside both visual references with an image viewer. The Inter font was confirmed loaded through the browser font API. Source and result screens had a document width equal to the 390 px mobile viewport, and no browser page errors were reported.

| Comparison | Final implementation |
| --- | --- |
| Palette | Near-black canvas, solid violet accents and lime actions match the selected references. No background gradients or glows were added. |
| Typography | Inter is served locally. Heavy, tightly tracked source and result headings preserve the editorial hierarchy. |
| Source composition | Large heading on the left, outlined dark-violet folder form on the right, followed by the explanation and sample band. |
| Flow rail | Four numbered steps remain visible; the current step uses a lime circle. A previous horizontal overflow defect was corrected. |
| Coverage | Amber warning remains prominent. Sample provenance is explicit and sits beside the warning on wide screens. |
| Results structure | Open summary with dividers, flat table, purple selected row and violet-bordered evidence inspector preserve the reference structure. |
| Evidence | Source hashes, destination identifiers, dates, sidecars and explanations use actual report fields. |
| Responsive behavior | Forms stack, headings wrap intentionally, controls remain operable and table overflow is contained within its own region. |

The copy review found no added promotional sections or eyebrow labels. Intentional differences from the static references are the actual report counts and paths, eight findings per page, additional evidence fields, visible saved scan history when it exists, and proper disabled actions before their prerequisites are met. The conceptual desktop window controls are omitted because window controls belong to the host application. Functional source-to-results checks and report correctness are documented separately in the testing notes.

The interface was faithfully checked against the selected visual system, with these explicit adaptations for real data and working controls.
