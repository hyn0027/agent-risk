"""Instantiate the universal NanoClaw ontology for one live session.

Entry point; the implementation lives in ``ontology.materialize``.
Run ``python3 materialize.py --help`` for options.
"""

from ontology.materialize.cli import main

if __name__ == "__main__":
    main()
