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
2. Clone your fork locally

    ```
    $ git clone git@github.com:your_name_here/sqladmin.git
    ```

3. Install [`uv`](https://docs.astral.sh/uv/) for project management. Install dependencies
   ```
   $ make setup
   ```

4. Install [`pre-commit`](https://pre-commit.com/) and apply it:

    ```
    $ pip install pre-commit
    $ pre-commit install
    ```

5. Create a branch for local development:

    ```
    $ git checkout -b name-of-your-bugfix-or-feature
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

8. Commit your changes and push your branch to GitHub:

    ```
    $ git add .
    $ git commit -m "Your detailed description of your changes."
    $ git push origin name-of-your-bugfix-or-feature
    ```

9.  Submit a pull request through the GitHub website.

## Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds functionality, the docs should be updated. Put
   your new functionality into a function with a docstring, and add the
   feature to the list in README.md.
3. The pull request should work from Python 3.9 till 3.14. Check
   https://github.com/smithyhq/sqladmin/actions
   and make sure that the tests pass for all supported Python versions.
