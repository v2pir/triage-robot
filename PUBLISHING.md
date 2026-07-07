# Publishing to PyPI

The package is publish-ready: metadata is complete, `python -m build` produces a
valid sdist + wheel, `twine check` passes, and a clean-venv install of the wheel
gives a working `triage` command. Two ways to actually push it to PyPI.

## Option A - one-time manual publish (fastest, do this first)

You need a PyPI account and an API token (PyPI → Account settings → API tokens).

```bash
pip install build twine
python -m build                       # -> dist/robot_triage-0.1.0{.tar.gz,-py3-none-any.whl}
python -m twine check dist/*          # sanity check
python -m twine upload dist/*         # username: __token__   password: <your PyPI token>
```

Then anyone can:

```bash
pip install robot-triage
triage run their-bag.mcap
```

## Option B - automated on every GitHub Release (no tokens)

`.github/workflows/publish.yml` publishes automatically via PyPI Trusted
Publishing. One-time setup:

1. On PyPI: **Account → Publishing → Add a pending publisher**
   - PyPI project name: `robot-triage`
   - Owner: `v2pir`
   - Repository: `triage-robot`
   - Workflow filename: `publish.yml`
2. Then cut a release:

```bash
# bump version in pyproject.toml first, then:
git tag v0.1.0 && git push origin v0.1.0
gh release create v0.1.0 --title "v0.1.0" --notes "First release"
```

The workflow builds and uploads - no secrets stored in the repo.

## Cutting later versions

1. Bump `version` in `pyproject.toml`.
2. `git commit` + tag `vX.Y.Z`.
3. Manual: `python -m build && twine upload dist/*`. Automated: create the GitHub Release.

PyPI rejects re-uploading an existing version, so always bump first.
