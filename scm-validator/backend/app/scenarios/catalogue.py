"""In-memory representation of a generated scenario suite."""
import hashlib

from ..core.models import Scenario


class ScenarioCatalogue:
    def __init__(self, scenarios: list[Scenario]):
        self.scenarios = scenarios
        self._by_id = {s.id: s for s in scenarios}

    def get(self, scenario_id: str) -> Scenario | None:
        return self._by_id.get(scenario_id)

    def by_category(self) -> dict[str, list[Scenario]]:
        out: dict[str, list[Scenario]] = {}
        for s in self.scenarios:
            out.setdefault(s.category, []).append(s)
        return out

    def suite_hash(self) -> str:
        """Stable fingerprint of the generated suite — used to verify determinism
        across repeated runs of the same repository."""
        h = hashlib.sha256()
        for s in sorted(self.scenarios, key=lambda x: x.id):
            h.update(s.id.encode())
            h.update(s.name.encode())
        return h.hexdigest()[:16]

    def __len__(self):
        return len(self.scenarios)

    def __iter__(self):
        return iter(self.scenarios)
