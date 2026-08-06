"""Rubric-based LLM judge (Phase 4).

Scores a finished trajectory along per-environment dimensions. Runs as a
separate pass after the match ends so it never contaminates objective
results. The sole scorer for judge-only environments like role-play.
"""
