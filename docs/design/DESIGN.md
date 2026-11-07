# SMARTPBL — Design Spec (for Tier 5)

The `screens/*.dc.html` files are the **source of truth for layout, copy and styling**. They are design-canvas files: plain HTML with inline styles, plus a small template syntax (`<sc-for>`, `<sc-if>`, `{{…}}`) and a `support.js` runtime you do **not** have.

**Do not reuse that runtime or syntax.** Read the files as a visual spec and rebuild the screens:
- coordinator screens in **React + TypeScript + Tailwind + shadcn/ui**
- carer screens in **Flutter** (Riverpod, GoRouter)

## 1. Design tokens

### Colours

| Token | Hex | Use |
|---|---|---|
| `bg` | `#F4F4F2` | App background (warm off-white) |
| `surface` | `#FFFFFF` | Cards, panels, rail |
| `surface-muted` | `#FAFAF9` | Inner tiles, list rows |
| `border` | `#E7E7E4` | Hairlines, outlines |
| `text` | `#18181B` | Primary text |
| `text-muted` | `#5F5F66` | Secondary text (passes 4.5:1 on white) |
| `primary` | `#111113` | Primary buttons, active nav, selected pills |
| `ai` | `#5B4FE9` / text `#3B32B8` / bg `#F6F5FF`, `#EEEDFD` | Anything AI-generated (sparkle icon) |
| `high` | text `#B42318` / bg `#FEF3F2` / border `#FECDCA` | High severity |
| `medium` | text `#93370D` / bg `#FFFAEB` / border `#FEDF89` | Medium severity, demo badge |
| `low-info` | text `#175CD3` / bg `#EFF8FF` | Low / informational |
| `success` | text `#067647` / bg `#ECFDF3` / border `#ABEFC6` | Passed checks, done |
| `elevated` | text `#C4320A` / bg `#FFF4ED` | Workforce "Elevated" risk |
| `shap-up` | `#EA580C` | Raises risk (SHAP) |
| `shap-down` | `#2563EB` | Lowers risk (SHAP) |
| Route colours | `#4338CA`, `#F97316`, `#0D9488` | One per carer on the map (they differ in lightness, not just hue) |
| Note highlights | falls `#FEEBD8`, nutrition `#DCEBFE`, mood `#EAE7FD` | Evidence spans in care notes |

### Typography
- **Inter** (400 / 500 / 600 / 700) everywhere.
- Page titles: 26–34 px, weight 700, letter-spacing −0.02em.
- Section titles: 15–18 px, weight 600.
- Body: 14–15 px. Meta: 12–13 px.
- Uppercase labels: 12 px, weight 600, letter-spacing 0.06–0.08em, muted colour.

### Shape and spacing
- Radius: cards 18–24 px, inner tiles 12–16 px, buttons and pills 999 px (fully round), table chips 6 px.
- Spacing is built on a 4 px base; card padding is 16–24 px and section gaps 16–28 px.
- Shadows are almost absent. Only the floating mobile nav uses `0 6px 24px rgba(17,17,19,0.10)`.
- Touch targets are at least 44 px. Mobile primary buttons are 54–56 px tall.

### Icons
Outline stroke icons at 1.75 stroke width. Use **lucide-react** in React and **lucide_icons** (or the equivalent) in Flutter. No emoji.

## 2. Screens → files → routes

| Screen | File | Route / app |
|---|---|---|
| Sign in | `Login.dc.html` | `/login` (web) |
| Overview | `Main.dc.html` | `/` (web) |
| Care-note review | `Review.dc.html` | `/review/:noteId` (web; the queue is its left panel) |
| Schedule & map | `Schedule.dc.html` | `/schedule` (web; the trade-off panel is on the right) |
| Carer risk detail | `Workforce.dc.html` | `/workforce/:carerId` (web; the list is its left panel) |
| Audit log | `Audit.dc.html` | `/audit` (web) |
| States sheet | `States.dc.html` | Reusable empty / loading / error / forbidden components |
| Carer sign in | `CarerLogin.dc.html` | Flutter `/login` |
| Today's visits | `Visits.dc.html` | Flutter `/` |
| Visit detail | `VisitDetail.dc.html` | Flutter `/visit/:id` |
| Write care note | `Note.dc.html` | Flutter `/visit/:id/note` |
| Note submitted | `Submitted.dc.html` | Flutter `/visit/:id/submitted` |

## 3. Shared layout (web)
- A 76 px white left rail with icon nav: Overview, Review, Schedule, Workforce, Audit. The active item is a black rounded square with a white icon.
- Content sits in a max-width 1240 px container. Pages stack to one column on narrow screens.
- A **"Demo data · synthetic"** badge is always visible on every screen.

## 4. Component mapping (shadcn/ui)

| Pattern in designs | Component |
|---|---|
| Pills, severity / status chips | `Badge` (custom variants: high, medium, low, success, ai, elevated) |
| Segmented controls (Travel / Balanced / Continuity, role switch) | `ToggleGroup` |
| Cards and panels | `Card` |
| Audit table | `Table`, with an expandable row (`Collapsible`) |
| Loading | `Skeleton` |
| Buttons | `Button` (default = primary black, `outline`, `ghost`) |
| Inputs | `Input`, `Label`, `Textarea` |
| Map | react-leaflet with OSM tiles. Routes are `Polyline`s; visits are numbered `DivIcon` markers |
| Charts (category bars, Pareto curve) | Recharts |
| SHAP chart | A custom diverging bar component (no library needed) |

## 5. Interaction rules
- Each AI output sits next to its source text, and evidence spans are highlighted in the note.
- Severity always shows as **text + colour** (never colour alone).
- Approve / Edit / Reject actions write to the audit log. "Escalate" appears for high severity.
- The workforce wording is supportive ("check-in", "rebalance"), never punitive.
- Forbidden routes render the access-denied state and log the attempt.

## 6. Flows to support in the demo
- **Carer:** sign in → today's visits → visit detail → write note → submitted.
- **Coordinator:** sign in → overview → review (approve) → audit entry visible.
- **Schedule:** change the priority → re-optimise → assignment reasons update.
