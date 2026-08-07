"""
Centralized icon system for the OneDrive PC Sync application.
Provides semantic icon names mapped to actual icon library icons.
"""

from PySide6.QtGui import QIcon
import qtawesome as qta


def get_icon(name: str) -> QIcon:
    """
    Get a QIcon for the given semantic name.

    Args:
        name: Semantic icon name (e.g., 'dashboard', 'folders', 'settings')

    Returns:
        QIcon object for the requested semantic name
    """
    # Mapping from semantic names to Font Awesome 5 free icon names
    icon_map = {
        # Navigation icons
        'dashboard': 'fa5s.tachometer-alt',
        'folders': 'fa5s.folder',
        'backup': 'fa5s.save',
        'scheduler': 'fa5s.calendar-alt',
        'logs': 'fa5s.list-alt',
        'settings': 'fa5s.cog',
        'about': 'fa5s.info-circle',

        # Action icons
        'sync': 'fa5s.sync-alt',
        'upload': 'fa5s.upload',
        'download': 'fa5s.download',

        # Status icons
        'success': 'fa5s.check-circle',
        'warning': 'fa5s.exclamation-triangle',
        'error': 'fa5s.times-circle',
        'running': 'fa5s.play-circle',
        'stopped': 'fa5s.stop-circle',

        # Utility icons
        'refresh': 'fa5s.sync',
        'restore': 'fa5s.undo-alt',
        'edit': 'fa5s.edit',
        'delete': 'fa5s.trash-alt',
        'browse': 'fa5s.folder-open',
    }

    # Get the icon name from the map, default to a question mark if not found
    icon_name = icon_map.get(name, 'fa5s.question-circle')
    return qta.icon(icon_name)