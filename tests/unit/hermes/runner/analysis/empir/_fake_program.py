"""Small fake EMPIR program used by process execution tests."""

import sys
import textwrap
from pathlib import Path


def write_fake_empir_program(executable: Path) -> None:
    """Write a program controlled by the contents of its first input file."""
    script = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import sys
        from pathlib import Path

        arguments = sys.argv[1:]
        input_value = arguments[arguments.index("-i") + 1]
        input_path = Path(input_value.split(",")[0])
        output_path = Path(arguments[arguments.index("-o") + 1])
        mode = input_path.read_text(encoding="utf-8").strip() or "success"

        print("o" * 5_000)
        print("e" * 5_000, file=sys.stderr)
        if mode == "nonzero":
            raise SystemExit(7)
        if mode != "missing_output":
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("generated", encoding="utf-8")
        """
    )
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text(script, encoding="utf-8")
    executable.chmod(0o755)
