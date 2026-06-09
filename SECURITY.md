# Security

Pavo works near sensitive audio, recording metadata, local credential stores,
and future Google Drive artifacts. Treat this repo as public and never commit
private recording data.

## Sensitive Data Rules

- Do not commit Plaud OAuth tokens.
- Do not commit Google credentials.
- Do not commit OpenAI credentials.
- Do not commit raw private recordings.
- Do not commit signed or temporary audio URLs.
- Do not paste voice fingerprints or speaker profile data into public issues.

Pavo local configuration belongs under:

```text
~/Eidos/Pavo/
```

Plaud credentials remain owned by the Plaud CLI under its own credential store.

## Reporting

Report security issues privately to the Eidos AGI maintainers. If a private
channel is not yet configured, contact the repository owner directly and avoid
posting exploit details, tokens, recordings, or personal data in public issues.
