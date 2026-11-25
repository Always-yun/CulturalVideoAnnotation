"""Reference eligibility shared by audits and image retrieval."""
from pathlib import Path


def eligible_reference_paths(symbol, root):
    """Use only explicitly enabled, reviewed, local reference records.

    Legacy unstructured paths have no review provenance and remain unavailable.
    """
    refs = symbol.get('reference_images') or []
    if not isinstance(refs, list):
        return []
    paths = []
    for ref in refs:
        if not isinstance(ref, dict) or ref.get('use_for_retrieval') is not True:
            continue
        if ref.get('verification_status') not in {'verified', 'human_verified', 'approved', 'reviewed'}:
            continue
        path = Path(ref.get('local_path') or '__missing__')
        path = path if path.is_absolute() else Path(root) / path
        if path.is_file():
            paths.append(str(path))
    return paths
