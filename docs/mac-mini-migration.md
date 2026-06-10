# Pavo Mac Mini Migration

Pavo is an Eidos project and should live on `mac-mini-01` under Daniel's single
Mac login when that machine is reachable. Eidos ownership should be represented
by repo, folder, service, and deployment boundaries, not by a second macOS user.

## Target

- Machine: `mac-mini-01`
- Account: `dshanklin`
- Home: `/Users/dshanklin`
- Destination root: `/Users/dshanklin/repos-eidos-agi/pavo`
- Data destination: `/Users/dshanklin/Eidos/Pavo`
- Marketplace checkout destination:
  `/Users/dshanklin/repos-eidos-agi/eidos-marketplace`
- Marketplace worktree destination:
  `/Users/dshanklin/.codex/worktrees/pavo-marketplace-ship`

## Source Surfaces

Copy these as one migration set:

- Repo: `/Users/dshanklinbv/repos-eidos-agi/pavo`
- Local Pavo data: `/Users/dshanklinbv/Eidos/Pavo`
- Canonical marketplace checkout:
  `/Users/dshanklinbv/repos-eidos-agi/eidos-marketplace/plugins/pavo`
- Canonical marketplace audit:
  `/Users/dshanklinbv/repos-eidos-agi/eidos-marketplace/AUDITS/pavo.md`
- Marketplace/plugin worktree:
  `/Users/dshanklinbv/.codex/worktrees/pavo-marketplace-ship`

The repo has a gitignored `.env.local` with private Railway/Pavo keys. It must
move through the private machine conduit, not chat or public docs.

Known local data size on 2026-06-10:

- Repo: 36 MB
- Eidos Pavo data folder: 411 MB
- Canonical marketplace Pavo plugin: 2.7 MB
- Marketplace worktree: 24 MB

Largest data areas:

- `/Users/dshanklinbv/Eidos/Pavo/cache/imports`: 241 MB
- `/Users/dshanklinbv/Eidos/Pavo/cache/plaud`: 133 MB
- `/Users/dshanklinbv/Eidos/Pavo/imports/youtube`: 20 MB
- `/Users/dshanklinbv/Eidos/Pavo/demos/conan-pavo-demo`: 14 MB

## Conduit Commands

Run these from any local shell once `mac-mini-01` answers SSH:

```bash
/Users/dshanklinbv/plugins/conduit/scripts/conduit doctor mac-mini-01 --account dshanklin

/Users/dshanklinbv/plugins/conduit/scripts/conduit run \
  --target mac-mini-01 \
  --account dshanklin \
  'mkdir -p ~/repos-eidos-agi/eidos-marketplace/AUDITS ~/.codex/worktrees ~/Eidos'

/Users/dshanklinbv/plugins/conduit/scripts/conduit sync \
  --target mac-mini-01 \
  --account dshanklin \
  /Users/dshanklinbv/repos-eidos-agi/pavo/ \
  /Users/dshanklin/repos-eidos-agi/pavo/

/Users/dshanklinbv/plugins/conduit/scripts/conduit sync \
  --target mac-mini-01 \
  --account dshanklin \
  /Users/dshanklinbv/Eidos/Pavo/ \
  /Users/dshanklin/Eidos/Pavo/

/Users/dshanklinbv/plugins/conduit/scripts/conduit sync \
  --target mac-mini-01 \
  --account dshanklin \
  /Users/dshanklinbv/repos-eidos-agi/eidos-marketplace/plugins/pavo/ \
  /Users/dshanklin/repos-eidos-agi/eidos-marketplace/plugins/pavo/

/Users/dshanklinbv/plugins/conduit/scripts/conduit sync \
  --target mac-mini-01 \
  --account dshanklin \
  /Users/dshanklinbv/repos-eidos-agi/eidos-marketplace/AUDITS/pavo.md \
  /Users/dshanklin/repos-eidos-agi/eidos-marketplace/AUDITS/pavo.md

/Users/dshanklinbv/plugins/conduit/scripts/conduit sync \
  --target mac-mini-01 \
  --account dshanklin \
  /Users/dshanklinbv/.codex/worktrees/pavo-marketplace-ship/ \
  /Users/dshanklin/.codex/worktrees/pavo-marketplace-ship/
```

Do not pass `--delete` for the first migration. The migration should preserve
remote files if the machine already has local Pavo state.

## Verification

After syncing:

```bash
/Users/dshanklinbv/plugins/conduit/scripts/conduit run \
  --target mac-mini-01 \
  --account dshanklin \
  'cd ~/repos-eidos-agi/pavo && git status --short --branch && python3 -m unittest discover -s tests'

/Users/dshanklinbv/plugins/conduit/scripts/conduit run \
  --target mac-mini-01 \
  --account dshanklin \
  'du -sh ~/repos-eidos-agi/pavo ~/Eidos/Pavo ~/repos-eidos-agi/eidos-marketplace/plugins/pavo ~/.codex/worktrees/pavo-marketplace-ship'

/Users/dshanklinbv/plugins/conduit/scripts/conduit proof --target mac-mini-01
```

## Current Blocker

On 2026-06-10, Conduit knew `mac-mini-01`, but SSH to `100.83.12.9:22` timed
out for `dshanklin`. The move is blocked until the Mac mini is online and
SSH/Tailscale accepts connections.
