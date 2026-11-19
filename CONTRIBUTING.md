# Contributing

Thanks for your interest in **breader-model-deploy**.

This repository is a **pull-only deploy pack**: Docker Compose, Caddy/authgate,
scripts, and docs that run pre-built images. Model training, labeling UI, and
most application source live in the full research repo, not here.

## How to help

- **Bugs / deploy issues** — open a [GitHub Issue](https://github.com/sscotti/breader-model-deploy/issues) with:
  - host OS / Docker version
  - relevant `.env` settings (redact tokens and passwords)
  - `docker compose ps` and the failing service’s logs
- **Docs** — typo and clarity PRs against `README.md`, `API.md`, or `TERMS.md` are welcome
- **Compose / scripts** — small, focused PRs that improve reliability or security without changing the clinical meaning of outputs

## Before you open a PR

1. Read [TERMS.md](TERMS.md) and [NOTICE](NOTICE) (upstream model licenses apply).
2. Do not commit secrets (`.env`, certs, `auth/users.basicauth`, Hub tokens).
3. Keep changes scoped; prefer one concern per PR.
4. Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## What this repo is not

- Not a place to retrain heads or swap foundation weights in-tree
- Not a certified medical device or NIOSH B-reader substitute
- Private Hub images (`sdscotti/breader-inference`) require maintainer-granted pull access

## Security

Please do **not** file public issues for vulnerabilities. See [SECURITY.md](SECURITY.md).

## Questions

Maintainer: Stephen Douglas Scotti — [sscotti@icloud.com](mailto:sscotti@icloud.com) · [GitHub](https://github.com/sscotti)
