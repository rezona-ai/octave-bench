"""Project-level utilities.

Submodules are imported explicitly to keep their dependencies isolated:

    from utils.tools import collect_source_code          # only stdlib
    from utils.eval_json import invoke_json_with_retry   # only stdlib
    from utils.llm_invoke import invoke_claude            # needs anthropic (reads .env itself)
"""
