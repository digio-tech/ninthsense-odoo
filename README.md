# ninthsense for Odoo

An Odoo 20 add-on for Recruitment. HR sends a hired applicant a 9thSense
onboarding link. The candidate uploads their documents, 9thSense reads them,
and **Create Employee** saves the new employee with every empty mapped field
filled from what was read.

- Onboarding templates choose which documents to collect and which document
  fills each employee field.
- Values from HR or Odoo are never overwritten, and a fill report on each
  request shows what was filled and what was skipped.
- Aadhaar numbers are stored masked.

Requires a 9thSense account and its onboarding portal. License: LGPL-3.

## Branches

| Branch | Purpose |
| --- | --- |
| `20.0` | Release branch for Odoo 20. The Odoo Apps store reads the module from here. |
| `develop` | Integration branch. Feature branches are squash-merged here, then `develop` is merged into `20.0` for a release. |

## Repository layout

| Path | What it is |
| --- | --- |
| `ninthsense/` | The Odoo module; the only thing that ships |
| `requirements.txt` | Python packages the module needs (`jsonschema`); Odoo.sh installs these |
| `scripts/check.sh` | The single quality gate: lint, dependency audit, unit tests, Odoo tests |
| `scripts/gen_contract_types.sh` | Regenerates `core/contract_types.py` from the vendored portal schemas |
| `scripts/requirements-dev.txt` | Packages the gate installs into the Odoo venv |

## Install

1. Put this repository on the Odoo server's `addons_path`.
2. `pip install -r requirements.txt` in Odoo's Python environment (Odoo.sh does
   this automatically).
3. Install **ninthsense** from Apps. It installs Recruitment,
   Employees and Skills if they are missing, and seeds the "Standard
   Onboarding" template, the document types and the email template.

## Configure

As an administrator, in **Recruitment → Configuration → Settings → 9thSense
Onboarding**:

- **Wrapper Address**: the `https://` origin of your 9thSense onboarding portal.
- **Shared Secret**: the secret the portal signs deliveries with (at least 32
  characters). It is write-only; the field is always empty when reopened.
- **Link Validity**: how many days a candidate link stays valid (default 14).

Configure an outgoing mail server so candidates receive the link. Without one,
HR can still copy the link from the dialog shown after **Send onboarding link**.

## Use

1. Move an applicant to a hired stage and click **Send onboarding link**. With
   more than one template, pick one; the default is preselected.
2. The candidate uploads documents through the link. The request moves to
   **Data received**.
3. Click **Create Employee**. The employee is saved with its empty fields
   filled, the documents attached, and the bank account and résumé lines
   created. The request moves to **Completed** and shows the fill report.

Requests are under **Recruitment → Onboarding**, and from the applicant's
**Onboarding** smart button. Templates are under **Recruitment → Configuration
→ Onboarding Templates**.

## Develop

The gate needs an Odoo 20 checkout with a `.venv`. By default it is this
repository's parent directory; set `ODOO_DIR` otherwise.

```sh
ODOO_DIR=/path/to/odoo PG_BIN=/opt/homebrew/opt/postgresql@16/bin scripts/check.sh
```

Code targets Python 3.12, the lowest version Odoo 20 supports.
