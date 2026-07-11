from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass
class VerificationResult:
    verified: bool
    consensus: str
    confidence: float
    dissent_indices: list[int]


class ResultVerifier:
    SIMILARITY_THRESHOLD = 0.6
    CONSENSUS_THRESHOLD = 0.5

    def compute_similarity(self, text1: str, text2: str) -> float:
        return SequenceMatcher(None, text1, text2).ratio()

    def find_consensus(self, results: list[str]) -> tuple[str, float, list[int]]:
        if not results:
            return ("", 0.0, [])
        if len(results) == 1:
            return (results[0], 1.0, [])

        n = len(results)
        sim_matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                sim = self.compute_similarity(results[i], results[j])
                sim_matrix[i][j] = sim
                sim_matrix[j][i] = sim

        avg_sims = [sum(sim_matrix[i]) / (n - 1) for i in range(n)]
        center_idx = avg_sims.index(max(avg_sims))
        consensus = results[center_idx]

        agree_indices = [
            i for i in range(n)
            if i == center_idx or sim_matrix[i][center_idx] >= self.SIMILARITY_THRESHOLD
        ]
        dissent_indices = [i for i in range(n) if i not in agree_indices]

        confidence = len(agree_indices) / n
        return (consensus, confidence, dissent_indices)

    def verify(self, worker_results: list) -> VerificationResult:
        valid = [r for r in worker_results if r.status.value == "completed" and r.content]
        if not valid:
            return VerificationResult(verified=False, consensus="", confidence=0.0, dissent_indices=[])

        contents = [r.content for r in valid]
        consensus, confidence, dissent_local = self.find_consensus(contents)

        valid_indices = [r.worker_index for r in valid]
        dissent_workers = [valid_indices[i] for i in dissent_local]

        verified = confidence >= self.CONSENSUS_THRESHOLD
        return VerificationResult(
            verified=verified,
            consensus=consensus,
            confidence=confidence,
            dissent_indices=dissent_workers,
        )
