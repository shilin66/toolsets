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
- `--warning-ink`: `#b45309` for compact warning text on light surfaces.
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
- The header always exposes the selected RPA environment as a prominent text-and-icon badge: blue for test and red for production. A first-time browser starts from the server default; later loads restore that browser's operator selection, and environment changes update the badge immediately.
- A single operational summary strip replaces equal-weight count cards. It prioritizes pending confirmation, report failures, today’s inbound mail, and latest-receipt freshness; actionable metrics navigate to their corresponding filtered work list.
- Summary metrics use one shared surface with internal dividers, tabular figures, neutral/default states, orange for pending work, red only for failures, and green only when a risk count is zero.

Toolbar:
- Search/filter inputs, primary action button, and reload button.
- Controls must not resize the table when values change.
- Supplier creation opens a modal dialog; supplier editing reuses the same dialog with populated fields.

Data table:
- Sticky header, horizontal overflow on small screens, empty and loading states.
- Text truncates in table cells and expands in details/edit forms.

Email read state:
- A shared compact status-and-action control appears in both the cutover email list and email detail metadata. It pairs an explicit `已读` / `未读` tag with the inverse action, so color never carries meaning alone.
- Unread uses the existing warning tone as an attention state; read uses the neutral info tone. The action uses the existing primary button treatment only when marking unread mail as read.
- While the IMAP update is pending, only the activated control is busy and repeat activation is disabled. On success the label swaps in place using the existing 160ms state transition; reduced-motion users receive the final state directly.
- The list toolbar includes an `全部 / 已读 / 未读` filter. A state change made while filtered reloads the list so rows that no longer match disappear immediately.

Cutover line matching:
- The processing-status cell starts with a persistent warning tag when any extracted line has no match. The tag pairs a warning SVG with explicit `未匹配线路` text and the line count, using the existing Element Plus light warning treatment.
- This warning remains visible alongside task statuses, including emails with no generated task. Matching uses the latest saved extraction and bindings, so resolving a match removes the warning on list refresh. Existing task validation is the fallback for older records without a saved matching payload.
- Warning content uses the metadata type size and base-unit spacing, stays on one line, and never replaces task status or task count.
- The processing-status filter includes `未匹配线路`. It selects emails with this same live warning, including emails with no task and partially matched tasks, combines with the other mail filters, and counts matches before pagination.

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

Dispatch session:
- The desktop-only session view uses one full-width semantic status panel above a two-column login and session-information workbench.
- Test and production are selected with one compact environment dropdown above the login-method selector; session validation, login attempts, captcha capture, and cutover reporting all use the same selected environment.
- Portal sessions are mutually exclusive across environments. A successful login to one environment invalidates the other environment's saved session before the new state is persisted.
- After login, the server periodically opens the selected environment's session-check URL in an isolated background context and atomically persists refreshed cookies. The existing session API exposes whether keepalive is waiting, active, expired, unavailable, paused, or disabled, plus its configured interval and most recent success.
- A queued or running cutover report pauses the current keepalive cycle. Keepalive resumes on a later interval only after the single-thread report queue becomes idle, so the scheduler does not start a session check while reporting work is already pending.
- Environment URLs come from server `.env` configuration. Each environment has an independent browser storage-state file, and an unconfigured environment is shown as unavailable without falling back to the other environment.
- Session states use the existing success, warning, danger, and muted tokens; color is always paired with text and an Element Plus icon.
- Login method selection is a two-option segmented control. The active method exposes its full user-entered form without environment labels.
- The operator login form is a centered, width-capped work surface with a distinct header, compact two-column field grid, contextual captcha note, and aligned footer actions. Password mode keeps its single captcha field to one readable column instead of stretching it across the full panel.
- Login inputs share a 44px control height. The captcha preview is a fixed 144px companion control, while the primary submit action remains visually dominant in the footer.
- The graphical captcha is a fixed-size image captured from the live RPA page and is refreshed within the same short-lived login attempt.
- Account, password, graphical captcha, and SMS code are transient form values. They are cleared after successful login and never shown in session metadata.
- The session page owns no cutover-task return action or pending-task continuation notice.
- Portal RPA performs only the page actions required for sign-in, session validation, background session keepalive, and reporting. Login and keepalive routes carry only the configured `ignoreDisableDevtool=true` query parameter; the RPA never opens developer tools, injects page scripts, monitors page traffic, or automatically reloads an operator-visible login or reporting page, and a blocked page fails for operator handling.
- Cutover reporting follows the task type: customer circuits use the generated Excel import, while backbone circuits fill the “传输一干” form from the confirmed `backbone_circuits` data and attach files from the source email. Each settled stage is captured under the report's business-identifier artifact directory; unknown dialogs stop for operator handling.
- Reporting opens the selected environment's target work page directly without a separate session-status preflight. A redirect to either login form is treated as `RPA_SESSION_REQUIRED` before any reporting action continues.
- Cutover reporting starts as a persisted background job. The task panel opens a non-modal right-side progress drawer that shows the current semantic stage, recorded operation steps, and settled screenshots as they arrive. Closing the drawer never interrupts the job; the operator can reopen it from the report-record header, and in-progress jobs resume polling when the task is reopened.
- Save and manual-confirm actions keep their buttons busy only while their own API request is in flight. The response state is applied immediately so the next valid action becomes available without waiting for a success toast or historical screenshot refresh.
- In the backbone form, selecting `中断` reveals the interruption-minutes input immediately beside the interruption-type selector. The input carries an inline `分钟` suffix, uses the calculated duration as its initial value, and disappears for `不中断` or `瞬断` without creating a separate labeled grid field.

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
