# Contributing

Contributions are welcome, and they are greatly appreciated! Every little bit
helps, and credit will always be given.

You can contribute in many ways:

## Types of Contributions

### Report Bugs

Report bugs at https://github.com/smithyhq/sqladmin/issues.

If you are reporting a bug, please include:

* Your operating system name and version.
* Any details about your local setup that might be helpful in troubleshooting.
* Detailed steps to reproduce the bug.

### Fix Bugs

Look through the GitHub issues for bugs. Anything tagged with "bug" and "help
wanted" is open to whoever wants to implement it.

### Implement Features

Look through the GitHub issues for features. Anything tagged with "enhancement"
and "help wanted" is open to whoever wants to implement it.

### Write Documentation

SQLAdmin could always use more documentation, whether as part of the
official SQLAdmin docs, in docstrings, or even on the web in blog posts,
articles, and such.

### Submit Feedback

The best way to send feedback is to file an issue at https://github.com/smithyhq/sqladmin.

If you are proposing a feature:

* Explain in detail how it would work.
* Keep the scope as narrow as possible, to make it easier to implement.
* Remember that this is a volunteer-driven project, and that contributions
  are welcome :)

## Get Started!

Ready to contribute? Here's how to set up `sqladmin` for local development.

1. Fork the `sqladmin` repo on GitHub.
2. Clone your fork locally and add the upstream remote:

    ```
    $ git clone git@github.com:your_name_here/sqladmin.git
    $ cd sqladmin
    $ git remote add upstream git@github.com:smithyhq/sqladmin.git
    ```

3. Install [`uv`](https://docs.astral.sh/uv/) for project management. Install dependencies:

    ```
    $ make setup
    ```

4. Install [`pre-commit`](https://pre-commit.com/) and apply it:

    ```
    $ pip install pre-commit
    $ pre-commit install
    ```

5. Always branch off `main`. Create a branch for local development following
   the [branch naming conventions](#branch-naming-conventions) below:

    ```
    $ git checkout main
    $ git pull upstream main
    $ git checkout -b fix/short-description-of-fix
    ```

    Now you can make your changes locally.

6. Apply linting and formatting, if not already done:

    ```
    $ make format
    ```

7. When you're done making changes, check that your changes pass the tests:

    ```
    $ make lint
    $ make test
    ```

    To run a specific test file or test case:

    ```
    $ uv run pytest tests/test_auth.py
    $ uv run pytest tests/test_auth.py::test_ajax_lookup_requires_auth
    ```

    To run tests with coverage report:

    ```
    $ uv run pytest --cov=sqladmin --cov-report=term-missing
    ```

    Note: test coverage must not drop below 95%.

8. Commit your changes following the [commit message conventions](#commit-message-conventions)
   and push your branch to GitHub:

    ```
    $ git add .
    $ git commit -m "fix: short description of your change"
    $ git push origin fix/short-description-of-fix
    ```

9. Submit a pull request through the GitHub website.

## Branch Naming Conventions

Always create branches from the latest `main`. Use one of the following
prefixes depending on the nature of your change:

| Prefix | When to use | Example |
|--------|-------------|---------|
| `fix/` | Bug fixes | `fix/uuid-primary-key-error` |
| `feat/` | New features | `feat/add-json-editor` |
| `docs/` | Documentation only changes | `docs/add-contributing-page` |
| `test/` | Adding or fixing tests only | `test/model-view-export-coverage` |
| `refactor/` | Code refactoring without behavior change | `refactor/simplify-model-converter` |
| `chore/` | Dependency bumps, CI, tooling | `chore/bump-starlette-to-0-50` |

Keep branch names lowercase and use hyphens, not underscores.
Each branch should address a single concern — do not mix a bug fix
and a new feature in the same branch.

## Commit Message Conventions

This project follows [Conventional Commits](https://www.conventionalcommits.org/).
The format is:

```
<type>: <short summary in present tense>
```

Common types:

| Type | When to use |
|------|-------------|
| `fix` | A bug fix |
| `feat` | A new feature |
| `docs` | Documentation changes |
| `test` | Adding or updating tests |
| `refactor` | Refactoring without behavior change |
| `chore` | Tooling, dependencies, CI |

If your commit closes a GitHub issue, reference it in the commit body:

```
feat: add json editor for json column fields

JSON column fields now render an interactive editor
instead of a plain textarea input.

Closes #1025
```

## Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds functionality, the docs should be updated. Put
   your new functionality into a function with a docstring, and add the
   feature to the list in README.md.
3. The pull request should work from Python 3.9 till 3.14. Check
   https://github.com/smithyhq/sqladmin/actions
   and make sure that the tests pass for all supported Python versions.
4. One pull request should address one concern. If you have multiple
   independent changes, open separate pull requests for each.
5. Link the related issue in your pull request description using
   `Closes #<issue-number>` or `Fixes #<issue-number>`.

## Project Structure

```
sqladmin/
├── sqladmin/              # source code
│   ├── application.py     # Admin class, route handlers
│   ├── models.py          # ModelView base class
│   ├── authentication.py  # AuthenticationBackend, login_required
│   ├── ajax.py            # AJAX lookup logic
│   └── ...
├── tests/                 # test suite
├── docs/                  # MkDocs documentation source
├── mkdocs.yml             # documentation site config
└── pyproject.toml         # project metadata and dependencies
```

## Keeping Your Fork Up to Date

Before starting any new work, sync your fork with upstream:

```
$ git checkout main
$ git pull upstream main
$ git push origin main
```
