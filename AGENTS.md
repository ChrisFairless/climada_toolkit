## Agent behaviour

- Ask clarifying questions.
- Write a plan before modifying code unless it's a fix or you're told to make the change right away.
- When I ask "Is there a way to do X?" I usually want an explanation of whether this is a good option. Not an implementation in the codebase.
- Update this file when asked to or you see relevant learnings.


## Purpose and structure

This repository is intended to be a library and package with code snippets that can be used with the CLIMADA model and modelling framework. Each standalone snippet of code is designed to provide:

- A python script which provides
    - A human-readable, simple(ish) amount of code that users can read, understand an adapt
    - An importable method that to reuse across projects
- An .ipynb notebook that
    - Shows the code in action
    - Can be compiled as part of the CI/CD testing

Each snippet lives in its own subfolder, and we make PLAN_*.md files there.

CLIMADA and CLIMADA Petals (with supplementary, less well-used tools) are attached to this VSCode workspace. Ask if you can't see them.


## Style

This repo is designed first to work as code snippets that users can copy and adapt.

As a rule we want to keep things copy-paste-able. That means
- Keeping conceptual blocks of code together
- Keeping this reusable code within the file that uses it. There may be a few exceptions for things that are used everywhere.
- Not splitting out reusable functionality into methods unless they are large or reused several times (splitting long tasks into subtasks such as download, preprocess, load, etc is good though)
- Not relying on a config file or environment variables. Instead set constants at the start of the script.
- Limiting package dependencies to the (pretty large) set of tools that CLIMADA imports
- Working with importable packages and methods, not classes

Sometimes this will feel like an antipattern or there will be a clearly better alternative that we should think about. Actively look for these and ask about them when they are relevant, the answer will usually be 'keep it simple', however.

As a rule if adding flexibility would add complexity (forked paths) ASK if we should (i) split this into multiple methods (re-using code is fine), or (ii) just choose the most common use case and implement for that.

We want to avoid complex python structures. Readability is key. Performance is a secondary concern.


## Testing

Keep unit testing light.

Test that imports work.

Integration testing (for now) is limited to a GitHub action that checks the notebooks are executable.
