"""Safety regulation parsing and processing domain."""

from srbg_api.safety_regulations.parser import MemSafetyRegulationParser
from srbg_api.safety_regulations.source import MemSafetyRegulationAdapter

__all__ = ["MemSafetyRegulationAdapter", "MemSafetyRegulationParser"]
