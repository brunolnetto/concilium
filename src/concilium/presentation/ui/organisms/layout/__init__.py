"""Main UI layouts and tabs for Streamlit application."""

from ._artifacts_tab import render_artifacts_tab
from ._bdi_editor import render_bdi_editor
from ._bdi_tab_indiretos import render_bdi_tab, render_indiretos_config
from ._cpu_composition_override import render_cpu_composition_override
from ._cpu_productivity_override import render_cpu_productivity_override
from ._cube_analytics import render_cube_analytics_by_version
from ._deliverables_config import render_deliverables_config
from ._diagnostico_backtracking import render_backtracking_pe, render_diagnostico_pe
from ._markdown_preview import render_markdown_report_preview
from ._mobilizacao_policy import render_mobilizacao_policy_editor
from ._ops_audit_compare import render_audit, render_compare, render_ops_audit_tab
from ._overview_tab import render_overview_tab
from ._planning_tab import render_planning_tab
from ._run_version_pipeline import (
    render_history,
    render_pipeline_monitor,
    render_run,
    render_version_management,
)
from ._saved_override import render_saved_override
from ._version_summary_detail import render_version_detail, render_version_summary
from ._version_wizard import render_version_wizard

__all__ = [
    "render_artifacts_tab",
    "render_audit",
    "render_backtracking_pe",
    "render_bdi_editor",
    "render_bdi_tab",
    "render_compare",
    "render_cpu_composition_override",
    "render_cpu_productivity_override",
    "render_cube_analytics_by_version",
    "render_deliverables_config",
    "render_diagnostico_pe",
    "render_history",
    "render_indiretos_config",
    "render_markdown_report_preview",
    "render_mobilizacao_policy_editor",
    "render_ops_audit_tab",
    "render_overview_tab",
    "render_pipeline_monitor",
    "render_planning_tab",
    "render_run",
    "render_saved_override",
    "render_version_detail",
    "render_version_management",
    "render_version_summary",
    "render_version_wizard",
]
