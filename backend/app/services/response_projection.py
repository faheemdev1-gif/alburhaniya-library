"""Small routine MCP replies; full diagnostics remain opt-in.

Canonical source text, identifiers and coordinate offsets are unchanged.
"""
from copy import deepcopy


def summarize_payload(payload, operation):
    result = deepcopy(payload)

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            # passage already contains this exact span. Keep coordinates and
            # text_version for verification without repeating its Arabic text.
            for key in ('source_span',):
                span = value.get(key)
                if isinstance(span, dict):
                    span.pop('source_quote', None)
            coordinate = value.get('coordinate_contract')
            if isinstance(coordinate, dict):
                coordinate.pop('text_sha256', None)
            for item in value.values():
                visit(item)
    if operation != 'search_library':
        visit(result)
    contract = result.get('contract')
    if isinstance(contract, dict):
        result['contract'] = {key: (value[:8] if key.endswith('digest') and isinstance(value, str) else value)
                              for key, value in contract.items()}
    return result
