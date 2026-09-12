# Brief: upgrade GymBot's Python and clear its dependency advisories

Paste this to a fresh agent. It is self-contained.

---

## What you are working on

`~/projects/GymBot` — a Telegram bot for gym groups, Hebrew-language, ~18 live groups.
Repo `AsafSH6/GymBot`, default branch `master`. **It is in production right now**, so
treat the running bot as something people notice when it breaks.

It runs as a Docker container on an EC2 host in AWS account `574921530352`
(eu-central-1), managed by Docker Compose — **not ECS**. Deploys go:

```
gh workflow run deploy.yml --ref master     # builds, pushes to ECR, deploys over SSM
```

`deploy.sh` on the host **automatically rolls back** to the previous image if the new
one fails its health check, and exits non-zero so CI goes red. That safety net is
tested and working — you can lean on it, but don't treat it as a substitute for
testing locally first.

Infra lives in a separate private repo, `AsafSH6/bots-infra`. You should not need to
touch it.

## The goal

1. Upgrade Python from **3.8** (end-of-life, no security updates) to a supported version.
2. Clear the **35 open Dependabot advisories** (14 high).

## What is already established — do not re-derive this

**Advisory breakdown** (verified via the Dependabot API):

| Package | Count | Comes from |
|---|---|---|
| tornado | 16 | a pin of `python-telegram-bot==13.7` |
| cryptography | 13 | a pin of `python-telegram-bot==13.7` |
| future | 1 (**high**) | unused Python-2-era leftover |
| Pygments | 2 | `ipython`, which is unused |
| ipython | 1 | unused, dev-only, shipped to production |
| dnspython | 1 | the mongo stack |
| pymongo | 1 | the mongo stack |

So **29 of 35 are unfixable without upgrading PTB**, and 4 are pure dead weight.

**Python compatibility, measured in clean containers:**

| Python | PTB 13.7 |
|---|---|
| 3.11 | imports fine |
| 3.12 | fails — `No module named 'urllib3'` |
| 3.13 | fails — `No module named 'imghdr'` (removed from the stdlib in 3.13) |

**3.11 is the ceiling while PTB stays at 13.7.** PTB's current release is **22.8**.

## Suggested staging — confirm with the owner before starting stage 2

**Stage 1 — low risk, no API changes.** Python 3.8 → 3.11. Delete the unused
packages. Bump `pymongo`/`dnspython`/`certifi`. Clears ~6 advisories and gets a
supported runtime. No application rewrite.

**Stage 2 — a real project.** PTB 13.7 → 22.x, which unlocks Python 3.13 and clears
the remaining 29. **PTB 20 was a complete rewrite from synchronous to async**: every
handler, task and decorator changes shape. Do not attempt this in the same pull
request as stage 1.

Note 3.11 is a waypoint, not a destination — it is itself supported only to late 2027.

## Traps that will cost you a day each

**The scheduling was rewritten days ago. Do not undo it.**
`gym_bot_app/tasks/task.py` now registers jobs on PTB's job queue instead of using
`threading.Timer`. `tests/test_schedule.py` has 12 tests pinning the behaviour, and
they are mutation-tested — they fail if you break any of it. Read them before touching
scheduling.

- **APScheduler 3.6.3 rejects `zoneinfo`.** It raises `TypeError: Only timezones from
  the pytz library are supported`. The code uses `pytz.timezone('Asia/Jerusalem')`
  deliberately. **If you upgrade PTB, APScheduler moves to 3.11+, which supports
  `zoneinfo` — that constraint changes, so re-verify rather than assuming either way.**
- **`days=(5,)` means Saturday.** APScheduler's cron is Monday=0. `gym_bot_app.DAYS_NAME`
  is Sunday-first, so `DAYS_NAME.index('Saturday')` is 6 — using it as a cron value
  schedules the weekly task on the wrong day. There is a regression test for this.
- **`target_time` must stay naive.** `gym_bot_app/commands/trained.py` compares it
  against a naive `datetime.now().time()`. Also, attaching a pytz zone to a
  `datetime.time` yields its Local Mean Time offset (+2:21 for Jerusalem), not +02:00.
- The four tasks are 09:00, 21:00, Saturday 21:30, 23:55 — **all Asia/Jerusalem**. The
  container sets `TZ`, and the Dockerfile asserts at build time that it resolves to
  IST/IDT so a missing `tzdata` fails the build rather than the deploy.

**A misconfigured bot silently destroys data.**
`gym_bot_app/decorators.py::run_for_all_groups` catches `Unauthorized` and calls
`group.delete()`, which is a soft delete (`is_deleted = True`). Every daily task runs
through it. **If you point the production bot at a database whose groups it is not a
member of, it flags them all deleted and the real bot goes silent.** In PTB 20+,
`telegram.error.Unauthorized` is renamed `Forbidden` — if you upgrade and miss the
rename, the handler stops catching it, which changes this behaviour in a way no test
will notice.

**Use the test bot. It exists precisely for this.**
`@TestGymBot` with its own Atlas cluster and database, entirely separate from
production. Switch the deployed config with:

```bash
cd ~/projects/bots-infra
./scripts/setup.sh --replace /bots/gymbot/BOT_TOKEN
./scripts/setup.sh --replace /bots/gymbot/MONGODB_URL_CON
```

Ask the owner for the test credentials. **Verify which bot and database you are
pointed at before every deploy** — this has already gone wrong once:

```bash
TOKEN=$(aws ssm get-parameter --name /bots/gymbot/BOT_TOKEN --with-decryption \
  --region eu-central-1 --query Parameter.Value --output text)
curl -s "https://api.telegram.org/bot${TOKEN}/getMe"
```

**Other landmines**

- `emoji==0.4.5` is from 2016 and its API changed completely at 1.0. Check how
  `gym_bot_app/__init__.py` uses it before bumping.
- `enum34`, `win-unicode-console`, `backports.*`, `pathlib2`, `ipaddress`,
  `singledispatch` are Python-2 shims. **`enum34` installs a package that shadows the
  stdlib `enum`** — harmless on 3.8 because the stdlib wins on `sys.path`, but delete
  them all; on newer Python they are a real hazard.
- `mongoengine` is **synchronous**. Under an async PTB it blocks the event loop.
  Probably fine at this scale, but it is a deliberate decision to make and record, not
  to discover.
- `requirements.txt` is a flat `pip freeze` with no separation of direct from
  transitive dependencies. Consider fixing that as part of the work — it is why
  unused packages survived this long.

## One lesson from the week this was written

Both bots were bitten repeatedly by **unpinned dependencies with no lockfile**. Local,
CI and the built image each resolve the newest release satisfying the range, so they
routinely differ. In the worst case a fresh image build pulled a major version of an
SDK that had removed a parameter the code passed, and the bot crashed on every message
while the deploy reported healthy.

`requirements.txt` here is fully pinned, which is why GymBot never hit that. **Keep it
pinned.** If this upgrade loosens anything, add a test that asserts the installed
library still provides what the code calls -- the pattern is
`tests/unit/test_sdk_compatibility.py` in the Glucosious repo, and it was verified to
fail against the bad version rather than merely written.

Also: the container health check is `GET / -> 200` and proves only that the process is
alive. It will not catch a broken bot. Verify by watching a real task fire.

## How to verify

The tests run **inside the built image**, against the exact pinned dependencies that
ship. That is how CI does it:

```bash
docker build -t gymbot:test .
docker run --rm gymbot:test python3 -c "import gym_bot_app.gym_bot"
docker run --rm -v "$PWD/tests:/app/tests:ro" gymbot:test \
  python3 -m unittest discover -s tests -t /app -v
```

Also print the schedule and confirm all four jobs report **IDT/+03:00** and that the
weekly one lands on a **Saturday** — the code for this is in
`.github/workflows/ci.yml` under "Report the schedule".

Before merging anything, deploy it to the **test** bot and watch a real task fire. The
09:00 and 21:00 slots come round daily; the Saturday 21:30 one is weekly, so assert its
next fire time rather than waiting for it.

## Ground rules

- Feature branch, one PR per stage. Never commit to `master` directly.
- Do not touch `bots-infra` or any AWS resource without asking.
- Do not deploy to the production bot without explicit approval, and never while
  pointed at a database the bot is not a member of.
- If you change scheduling behaviour, update `tests/test_schedule.py` to pin the new
  behaviour — do not delete assertions to make them pass.
