"""robot-triage: auto-flag common-sense failures in robot logs (.mcap / .bag).

Four small stages, each in its own module, wired together by the CLI:

    reader    -> yields (topic, t, msg) from a bag         (Stage 1)
    detectors -> turn messages into Events                 (Stage 2)
    report    -> text / html for a human                   (Stage 3/4)
    replay    -> cut a clip around each Event

``events.Event`` is the shared vocabulary that keeps the stages decoupled.
"""

__version__ = "0.1.0"
