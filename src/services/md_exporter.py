"""Markdown task list exporter — writes tasks as one canonical Markdown line each."""

from __future__ import annotations

from ..models.task import Task


class MarkdownExporter:
    """Export tasks to a ``.md`` file, one ``raw_md`` line per task."""

    @classmethod
    def export_to_file(cls, tasks: list[Task], path: str) -> int:
        """Write every task's raw_md line to ``path``. Returns task count."""
        with open(path, "w", encoding="utf-8") as f:
            for task in tasks:
                f.write(task.raw_md + "\n")
        return len(tasks)

    def export_file(self, tasks: list[Task], path: str) -> int:
        """Instance form — mirrors the batch-export call style."""
        return self.export_to_file(tasks, path)
