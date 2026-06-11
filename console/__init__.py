"""Infra console: operator dashboard + CLI over Ansible (spike).

Layout rule (binding, see openspec/changes/infra-console-spike/design.md D1):
- console.core    internal layer — pure Python, never imports FastAPI/uvicorn/argparse wiring
- console.cli     interface adapter #1 (argparse -> core)
- console.app     interface adapter #2 (HTTP -> core, marshalling only)
"""
