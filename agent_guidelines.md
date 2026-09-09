## Agent behaviour

- Ask clarifying questions.
- Write a plan before modifying code unless it's a fix or you're told to make the change right away.
- Update this file when asked to or you see relevant learnings.

## Style

This repo is designed first to work as code snippets that users can copy and adapt.

As a rule we want to keep things copy-paste-able. That means
- keeping conceptual blocks of code together
- being careful about when we split re-used code into a separate method
- keeping this reusable code in the file that uses it. There may be a few exceptions for things that are used everywhere.

As a rule if adding flexibility would add complexity (forked paths) ASK if we should (i) split this into multiple methods (re-using code is fine), or (ii) just choose the most common use case and implement for that.

The second priority is to build this out as a python package where the user can import these methods and call them for common use cases without extensive configuration.

We want to avoid importing additional packages not already used in CLIMADA.

We want to avoid complex python structures. Readability is key. Performance only matters when we might work with very large datasets that a laptop would need to chunk.


## Testing

Testing should remain light.

Test that imports work.

Integration testing is the main thing. We'll come up with bespoke examples for this. Ask before you write them.