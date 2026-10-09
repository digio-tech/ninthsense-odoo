==========
ninthsense
==========

.. |badge1| image:: https://img.shields.io/badge/license-LGPL--3-blue.png
    :target: http://www.gnu.org/licenses/lgpl-3.0-standalone.html
    :alt: License: LGPL-3
.. |badge2| image:: https://img.shields.io/badge/github-digio--tech%2Fninthsense--odoo-lightgray.png?logo=github
    :target: https://github.com/digio-tech/ninthsense-odoo/tree/20.0/ninthsense
    :alt: digio-tech/ninthsense-odoo

|badge1| |badge2|

Collect a hired applicant's documents through 9thSense, then let Create
Employee fill the new employee from them.

HR sends the applicant an onboarding link from the applicant form. The
candidate uploads their documents in the 9thSense onboarding portal, 9thSense
reads them, and the portal delivers the documents and the values read back to
Odoo. When HR clicks **Create Employee**, the employee is saved with every
empty mapped field filled: personal details, address, identity numbers,
passport, bank account and résumé lines.

* Onboarding templates choose which documents to collect and which document
  fills each employee field, edited with dropdowns.
* Values set by HR or by Odoo are never overwritten. Each request keeps a fill
  report of what was filled and what was skipped, and why.
* Aadhaar numbers are stored masked to their last four digits.

A 9thSense account and its onboarding portal are required.

**Table of contents**

.. contents::
   :local:

Configuration
=============

#. Install the Python package ``jsonschema`` in Odoo's environment. Odoo.sh
   installs it from the repository's ``requirements.txt``.
#. As an administrator, open **Recruitment → Configuration → Settings →
   9thSense Onboarding** and set:

   * **Wrapper Address**: the ``https://`` origin of your 9thSense onboarding
     portal.
   * **Shared Secret**: the secret the portal signs its deliveries with, at
     least 32 characters. It is write-only and shows empty when reopened.
   * **Link Validity**: how many days a candidate link stays valid (14 by
     default).

#. Configure an outgoing mail server so candidates receive their link. Without
   one, HR can copy the link from the dialog shown after sending.
#. Review **Recruitment → Configuration → Onboarding Templates**. The
   installed "Standard Onboarding" template is the default; add templates for
   other kinds of hires.

Usage
=====

#. Move an applicant to a hired stage and click **Send onboarding link**. With
   several templates, pick one; the default is preselected.
#. The candidate uploads their documents through the link. The request moves
   to **Data received**.
#. Click **Create Employee**. The employee is saved with its empty fields
   filled, the documents are attached, and the bank account and résumé lines
   are created. The request moves to **Completed** and shows its fill report.

Requests are listed under **Recruitment → Onboarding** and open from the
applicant's **Onboarding** smart button.

Known issues / Roadmap
======================

* The documents and the fields read from them are Indian: Aadhaar, PAN,
  IFSC, Indian states and PIN codes.
* One 9thSense portal per database: the wrapper address and secret are shared
  by all companies, while the requests themselves follow each company.
* Uploaded documents are kept as the candidate sent them, so an Aadhaar card
  image still shows its full number.

Bug Tracker
===========

Bugs are tracked on `GitHub Issues
<https://github.com/digio-tech/ninthsense-odoo/issues>`_. Please check whether
your issue has already been reported before opening a new one.

Credits
=======

Authors
-------

* Digio Labs

Maintainers
-----------

This module is maintained by Digio Labs, as part of the
`digio-tech/ninthsense-odoo <https://github.com/digio-tech/ninthsense-odoo/tree/20.0/ninthsense>`_
project on GitHub.
