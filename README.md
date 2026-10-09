# ninthsense for Odoo

[![License: LGPL-3](https://img.shields.io/badge/license-LGPL--3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.html)
[![Odoo 20.0](https://img.shields.io/badge/Odoo-20.0-714B67.svg)](https://github.com/digio-tech/ninthsense-odoo/tree/20.0)

Odoo integration for 9thSense onboarding. HR sends a hired applicant a 9thSense
onboarding link, the candidate uploads their documents, and **Create Employee**
saves the new employee with every empty field filled from what 9thSense read.

## Available addons

| addon | version | summary |
| --- | --- | --- |
| [ninthsense](ninthsense/) | 20.0.1.0.0 | Collect a hired applicant's documents through 9thSense and fill the new employee |

The module's own [README](ninthsense/README.rst) covers configuration, usage
and known issues in full.

## Requirements

- Odoo 20.0, Community or Enterprise, self-hosted or Odoo.sh. Odoo Online
  cannot install it, because it needs the Python package below.
- The Python package `jsonschema`, listed in [`requirements.txt`](requirements.txt).
- A 9thSense account and its onboarding portal.

## Installation

1. Add this repository to the Odoo server's `addons_path`.
2. Install the requirements in Odoo's Python environment:
   `pip install -r requirements.txt`. Odoo.sh does this automatically.
3. In **Apps**, install **ninthsense**. It installs Recruitment, Employees and
   Skills if they are missing, and seeds the "Standard Onboarding" template,
   the document types and the email template.

## Configuration and usage

Set the 9thSense portal address and shared secret in **Recruitment →
Configuration → Settings → 9thSense Onboarding**. Then move an applicant to a
hired stage, click **Send onboarding link**, and once the candidate's documents
arrive, click **Create Employee**. The details are in the
[module README](ninthsense/README.rst).

## Bug tracker

Report bugs on [GitHub Issues](https://github.com/digio-tech/ninthsense-odoo/issues).

## Development

| Branch | Purpose |
| --- | --- |
| `20.0` | Release branch for Odoo 20. The Odoo Apps store publishes from it. |
| `develop` | Integration branch. Feature branches are squash-merged here. |
| `main` | Default branch; follows `20.0` at each release. |

To release, merge `develop` into `20.0` and `main`, bump `version` in
`ninthsense/__manifest__.py`, and push.

`scripts/check.sh` is the single quality gate: lint, dependency audit, unit
tests and the Odoo test suite on a throwaway database. It needs an Odoo 20
checkout with a `.venv`, by default this repository's parent directory, or
wherever `ODOO_DIR` points:

```sh
ODOO_DIR=/path/to/odoo PG_BIN=/opt/homebrew/opt/postgresql@16/bin scripts/check.sh
```

`scripts/gen_contract_types.sh` regenerates `ninthsense/core/contract_types.py`
from the vendored portal schemas. Code targets Python 3.12, the lowest version
Odoo 20 supports.

## Credits

Developed and maintained by Digio Labs.

## License

[LGPL-3](LICENSE).
