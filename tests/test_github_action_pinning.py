import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PINNED_ACTION = re.compile(r"^\s*uses:\s*[^\s@]+@[0-9a-f]{40}(?:\s+#.*)?$")


class GitHubActionPinningTests(unittest.TestCase):
    def test_external_actions_are_pinned_to_commit_shas(self) -> None:
        unpinned: list[str] = []
        for workflow in sorted(WORKFLOWS.glob("*.yml")):
            for line_number, line in enumerate(workflow.read_text().splitlines(), start=1):
                if "uses:" not in line or line.lstrip().startswith("#"):
                    continue
                if not PINNED_ACTION.fullmatch(line):
                    unpinned.append(f"{workflow.relative_to(ROOT)}:{line_number}: {line.strip()}")

        self.assertEqual([], unpinned, "unpinned GitHub Actions:\n" + "\n".join(unpinned))


if __name__ == "__main__":
    unittest.main()
