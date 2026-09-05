"""Scientific domains built on the universal Scientific Core contracts.

A domain owns its physics, its components and its solver adapters. It never
adds domain-specific fields to the universal IR: everything here is a
*consumer* of ``engcore.scientific``, never a modifier of it.
"""
