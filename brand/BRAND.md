# agent-harness brand kit

Only what the project needs: a name, a tagline, a logo, colours, fonts, and how to use them in the README, terminal, Streamlit page and demo video.

## Name and tagline
- **Name:** `agent-harness` (always lowercase, with the hyphen)
- **Tagline:** A small multi-agent harness with budgets, retries, safety controls and replayable logs.
- **Short tagline (video title card):** A team of agents, kept in check.

## Logo
`brand/logo.svg`: one lead node (teal) feeding three worker nodes (white) inside a rounded frame, which is the harness.
- Use it at the top of the README and as the Streamlit page icon.
- Do not recolour, stretch or add effects.

## Colours

| Role | Hex | Used for |
|---|---|---|
| Background | `#0F172A` | Page background, logo frame |
| Surface | `#1E293B` | Cards, sidebar, trace panel |
| Text | `#F8FAFC` | Main text |
| Muted text | `#94A3B8` | Timestamps, labels |
| Accent (teal) | `#14B8A6` | Buttons, links, the lead agent |

### Status colours (match the harness states)

| State | Hex | Rich colour | Meaning |
|---|---|---|---|
| OK / COMPLETE | `#22C55E` | `green` | Step or run succeeded |
| RETRY / PARTIAL | `#F59E0B` | `yellow` | Retrying, or run finished with gaps |
| ERROR / STOPPED / DENIED | `#EF4444` | `red` | Failure, limit hit, tool denied |
| INJECTION SUSPECTED | `#A855F7` | `magenta` | A file tried to give orders |
| APPROVAL NEEDED | `#38BDF8` | `cyan` | Waiting for a human yes/no |

Always pair a colour with a word or icon (e.g. `PARTIAL`, `DENIED`), never colour alone.

## Fonts
- **UI and README:** the default system sans-serif (no font downloads needed).
- **Traces, code, IDs:** the default monospace font.

## Where to apply it
- **README:** logo + name + tagline at the top, then status colours as text labels.
- **Terminal (`replay.py`, `run.py`):** Rich colours from the status table above.
- **Streamlit (`app.py`):** copy `brand/config.toml` to `.streamlit/config.toml`; page title `agent-harness`, page icon `brand/logo.svg`.
- **Demo video:** first slide = logo, name and short tagline on the background colour.
