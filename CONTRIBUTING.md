# Contributing

Pavo is an Eidos AGI tool for capturing Plaud recordings, preserving real audio,
and routing recordings through local transcription intelligence.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
python3 -m unittest discover -s tests
```

Install the Plaud CLI separately when testing live Plaud behavior:

```bash
npm install -g @plaud-ai/cli
plaud login
```

## Contribution Rules

- Keep Plaud, Google, and OpenAI credentials out of the repo.
- Keep durable behavior in the Pavo CLI/package.
- Keep Codex, Claude, and MCP plugin shims thin.
- Prefer manifest-backed evidence over transcript-only behavior.
- Add or update tests for behavioral changes.
- Do not include raw private recordings, signed URLs, tokens, or voice profile
  data in issues, commits, logs, or docs.

## Verification

Before opening a PR or shipping a change, run:

```bash
python3 -m unittest discover -s tests
pavo doctor
```
