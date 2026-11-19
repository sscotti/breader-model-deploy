# Security policy

## Supported versions

Security fixes are applied to the current `main` branch of this deploy pack and
to the Docker Hub tags documented in [README.md](README.md) (typically `:amd64`
/ `:arm64` / `:latest` for the public images). Older tags are not patched.

## Scope

This repository ships Compose, reverse-proxy, and glue around third-party and
private images. Please report:

- Exposure of secrets, Basic Auth bypass, or TLS misconfiguration in this pack
- Unsafe defaults in `docker-compose.yml`, Caddy, or authgate
- Issues that could lead to unauthorized access to the Gradio UI, Orthanc, or
  uploaded imaging data on a deployed host

Out of scope (still welcome as private notes, but may be redirected):

- Model accuracy / clinical performance (not a security issue)
- Upstream Ark, CXAS, Google ELIXR, or Orthanc vulnerabilities (report upstream
  when possible; we will track relevant image rebuilds)

## Reporting a vulnerability

**Do not open a public GitHub issue.**

Email **sscotti@icloud.com** with:

- A short description of the issue and impact
- Steps to reproduce (or a proof-of-concept)
- Affected tag / commit if known
- Whether you plan a public disclosure date

You should receive an acknowledgement within a few business days. We will work
with you on a fix and coordinated disclosure when appropriate.

## Operational guidance for operators

- Keep `CADDY_BASIC_AUTH=true` (or equivalent access control) on any
  internet-facing deploy
- Do not commit or share `.env`, TLS private keys, or `auth/users.basicauth`
- Prefer Cloudflare **Full (strict)** with an Origin CA cert when proxying
- Treat uploaded DICOM/PNG as sensitive; the demo stack is for research /
  education, not production PHI workflows without your own hardening and
  legal review
