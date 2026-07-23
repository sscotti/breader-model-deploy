# Terms of use (assembled stack)

**Effective for:** `breader-model-deploy` and the associated Docker Hub images
(`sdscotti/breader-inference`, `sdscotti/cxr-preprocess-api`, `sdscotti/orthanc-breader`).

## Your original code

Compose files, Orthanc ILO plugin packaging, scripts, and documentation in this
repository are Copyright 2026 Stephen Douglas Scotti and licensed under the
[Apache License, Version 2.0](LICENSE).

## Assembled stack (models + images)

By pulling or running the stack you acknowledge:

1. **Intended use.** Research and education / decision-support and teaching aid
   only. Not a medical device. Not a substitute for a certified [NIOSH B Reader](https://www.cdc.gov/niosh/chestradiography/php/about/)
   or clinical judgment.
2. **No endorsement.** NIOSH / CDC, Arizona State University (Ark), Google
   (HAI-DEF), and CXAS authors do not endorse this software.
3. **Upstream terms control model weights.** Ark, optional Google CXR Foundation
   (ELIXR), and CXAS remain under their own licenses. See [NOTICE](NOTICE).
   In particular:
   - **Ark** — non-commercial / academic research under the ASU GitHub Project
     License unless you obtain a separate commercial agreement from ASU.
   - **Google ELIXR / CXR Foundation** — [HAI-DEF Terms of Use](https://developers.google.com/health-ai-developer-foundations/terms)
     and [Prohibited Use Policy](https://developers.google.com/health-ai-developer-foundations/prohibited-use-policy).
   - **CXAS** — non-commercial use per the upstream project’s terms.
4. **Commercial use.** Do not commercially deploy the full stack (or Ark /
   CXAS components) unless you have secured all required upstream rights and
   any applicable health regulatory authorizations.
5. **AS IS.** Software and outputs are provided without warranty. You assume
   all risk from use or redistribution.

Redistributors must retain `LICENSE`, `NOTICE`, and this file (or equivalent
conspicuous notice of the same terms).
