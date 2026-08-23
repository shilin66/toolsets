# Mail Listen Admin Design

## 1. Product Surface

This is an internal NOC operations console for supplier configuration, email record lookup, and ticket record lookup. The interface prioritizes repeated work, scanning, filtering, and quick edits over marketing impact.

## 2. Visual Direction

Data-dense SaaS operations console with a blue-white service palette, white work surfaces, cool blue navigation accents, compact controls, and high-contrast tables. The memorable moment is the single-screen operations wall: fixed navigation, live summary strip, and full-width work surfaces that keep supplier, email, and ticket data scannable without a black theme.

## 3. Tokens

Colors:
- `--bg`: `#f8fafc`
- `--bg-rail`: `#eff6ff`
- `--panel`: `#ffffff`
- `--panel-raised`: `#ffffff`
- `--panel-muted`: `#f1f5f9`
- `--ink`: `#0f172a`
- `--muted`: `#64748b`
- `--line`: `#dbe7f3`
- `--accent`: `#2563eb`
- `--accent-strong`: `#1d4ed8`
- `--danger`: `#dc2626`
- `--warning`: `#f97316`
- `--success`: `#16a34a`
- `--focus`: `#0ea5e9`

Typography:
- UI font: `Fira Sans` if available, then native sans stack for fast loading and legible CJK text.
- Mono font: `Fira Code` if available, then native monospace stack for IDs, timestamps, and codes.
- Page title: 24px, 700.
- Section title: 16px, 700.
- Body: 14px, 400.
- Table text: 13px, 400.
- Metadata: 12px, 500.

Spacing:
- Base unit: 4px.
- Compact gap: 8px.
- Standard gap: 12px.
- Panel padding: 16px.
- Page padding: 20px.

Shape:
- Buttons and inputs: 6px radius.
- Panels and modals: 8px radius.
- Tables: square internal grid, 8px outer panel.

## 4. Layout

Desktop uses a two-column app shell: 248px left navigation and a flexible content area. The primary target is a 1280px-or-wider NOC operations desktop. Mobile is not a product requirement.

Supplier configuration uses one centered vertical stack at every workspace width. The stack is fluid up to 2160px so 1366px, 1440px, 1920px, and 2560px workspaces use the available width without creating oversized side gutters. Each configuration region is independently collapsible and defaults to expanded. Dynamic custom-field lists stay in the document flow without an internal scrollbar.

The supplier form does not repeat the page title inside a second card. A lightweight breadcrumb sits above the form, while cancel/save actions are integrated into the basic-information section header without adding another container or covering editable content.

## 5. Primitives

App shell:
- Sidebar navigation with selected, hover, and focus states.
- Header strip with API key input, reload command, and status message.
- A single operational summary strip replaces equal-weight count cards. It prioritizes pending confirmation, report failures, today’s inbound mail, and latest-receipt freshness; actionable metrics navigate to their corresponding filtered work list.
- Summary metrics use one shared surface with internal dividers, tabular figures, neutral/default states, orange for pending work, red only for failures, and green only when a risk count is zero.

Toolbar:
- Search/filter inputs, primary action button, and reload button.
- Controls must not resize the table when values change.
- Supplier creation opens a modal dialog; supplier editing reuses the same dialog with populated fields.

Data table:
- Sticky header, horizontal overflow on small screens, empty and loading states.
- Text truncates in table cells and expands in details/edit forms.

Dialog form:
- Supplier create/edit form with labeled inputs, checkbox, textarea, save/cancel actions.
- Modal width is capped for comfortable prompt editing, with a clear close affordance and Escape dismissal.
- Validation and API errors render in the status area, not as browser alerts.
- Long editable field lists grow with the page, with the item count kept visible in the collapsible section header.

Fixed-field rule workbench:
- Fixed fields are selected from a responsive tab grid above one full-width editor; never pair independently expanding editors in the same grid row.
- The selected field uses a soft blue tonal state, an explicit `aria-selected` state, and arrow-key navigation.
- Every field tab permanently exposes either `已配置` or `使用默认`; the section header summarizes both counts so configuration coverage is visible without opening fields.
- Only the active rule editor is shown, with required/optional metadata, the same persistent configuration status, and a clear restore-default action.
- Rule textareas use a compact 8px blue-gray scrollbar with a stronger blue hover state.

Supplier form commands:
- The breadcrumb is borderless and subordinate to the app header, avoiding a duplicated page-title card.
- Cancel/save live in the basic-information section header and stop click propagation so using them never toggles the section.

Buttons:
- Primary: blue fill.
- Secondary: white fill with blue-gray border.
- Danger: white fill with red text and border.
- Icon-free text buttons are acceptable here because actions are explicit operational commands.

## 6. Accessibility

All controls use native buttons, inputs, labels, and tables. Focus rings use `--focus`. Chinese labels must not clip or rely on narrow fixed widths in the desktop console.

State transitions are limited to 160ms color, border, and background changes. Reduced-motion users receive the final state without transition.

## 7. Accepted Debt

This first admin frontend is vanilla HTML/CSS/JS served by Flask to avoid adding a separate frontend build pipeline. If the console grows beyond these three resources, split into a real frontend app and component modules.
