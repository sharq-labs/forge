"""Model-to-measurement validation.

This file exists so that ``audit`` inside this round can be imported by a
fully-qualified path. Two assurance rounds now ship a top-level package called
``audit``, both round directories end up on ``sys.path`` when the whole
benchmarks tree is collected in one pytest session, and whichever is imported
first claims the bare name. A test that says ``from audit import ...`` gets
whichever round won that race -- which is an ImportError on a good day and a
silent comparison against another round's code on a bad one.
"""
