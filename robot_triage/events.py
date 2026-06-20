from dataclasses import dataclass

@dataclass
class Event:
    t_start: float        # seconds into the bag
    t_end: float
    severity: str         # "info" | "warn" | "critical"
    detector: str         # which detector fired
    summary: str          # one human sentence: "topic /camera/image silent for 4.2s"
    details: dict         # anything extra (topic name, gap length, msg counts)