"""
Centralized icon system for EverySync.
Provides semantic icon names mapped to actual icon library icons.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
import qtawesome as qta
from ..themes import colors


def get_app_icon(state=None) -> QIcon:
    """EverySync mark, optionally carrying the existing tray status."""
    icon = QIcon(str(Path(__file__).with_name("app.svg")))
    if state is None:
        return icon
    badge_color, badge_symbol = {
        "idle": (colors.TEXT_SECONDARY, "pause"),
        "running": (colors.ICON_PRIMARY, "play"),
        "success": (colors.SUCCESS, "check"),
        "error": (colors.ERROR, "cross"),
    }[state]
    result = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        pixmap = icon.pixmap(size, size)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size / 64, size / 64)
        painter.setPen(QPen(QColor(colors.BACKGROUND), 2))
        painter.setBrush(QColor(badge_color))
        painter.drawEllipse(QRectF(40, 40, 23, 23))
        painter.setPen(QPen(QColor(colors.BACKGROUND), 2.5,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        if badge_symbol == "pause":
            painter.drawLine(48, 48, 48, 56)
            painter.drawLine(55, 48, 55, 56)
        elif badge_symbol == "play":
            painter.drawLine(49, 47, 56, 52)
            painter.drawLine(56, 52, 49, 57)
            painter.drawLine(49, 57, 49, 47)
        elif badge_symbol == "check":
            painter.drawLine(46, 52, 50, 56)
            painter.drawLine(50, 56, 57, 48)
        else:
            painter.drawLine(48, 48, 56, 56)
            painter.drawLine(56, 48, 48, 56)
        painter.end()
        result.addPixmap(pixmap)
    return result


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
        'folder': 'fa5s.folder',
        'folder-plus': 'fa5s.folder-plus',
        'folder-open': 'fa5s.folder-open',
        'backups': 'fa5s.archive',
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
        'open': 'fa5s.folder-open',
        'toggle-on': 'fa5s.toggle-on',
        'toggle-off': 'fa5s.toggle-off',
        'cloud': 'fa5s.cloud',
    }

    # Get the icon name from the map, default to a question mark if not found
    icon_name = icon_map.get(name, 'fa5s.question-circle')
    return qta.icon(icon_name, color=colors.ICON_PRIMARY,
                    color_active=colors.SELECTED_TEXT,
                    color_disabled=colors.TEXT_DISABLED)
