"""Tadado CLI — headless command-line gateway for the Claude Code skill.

Entry point: :func:`src.cli.headless.run_cli`.  Commands are forwarded to a
running GUI instance when one exists; otherwise they execute headless over
the same ``TaskService`` seam the GUI uses.
"""
