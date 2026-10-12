from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QLabel
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt
from pyqtgraph import PlotWidget, mkPen


class SyncChartWidget(PlotWidget):
    """
    A reusable chart widget for visualizing sync activity over time.
    Accepts data via set_data() method and displays a line chart with points.
    Designed for dark theme with minimal grid and modern appearance.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Initialize the chart appearance."""
        # Import theme colors
        from ..themes import colors
        from ..themes import typography

        # Dark background
        self.setBackground(colors.SURFACE)

        # Set axis styles
        axis_pen = mkPen(color=colors.BORDER, width=1)
        self.getAxis('left').setPen(axis_pen)
        self.getAxis('bottom').setPen(axis_pen)
        self.getAxis('left').setTextPen(colors.TEXT_SECONDARY)
        self.getAxis('bottom').setTextPen(colors.TEXT_SECONDARY)
        for name in ('left', 'bottom'):
            self.getAxis(name).setStyle(tickFont=QFont("Segoe UI", typography.FONT_SIZE_XSMALL))

        # Grid lines - subtle
        self.showGrid(x=True, y=True, alpha=0.15)

        # Enable antialiasing for smooth rendering
        self.setAntialiasing(True)

        # Set minimum size for visibility
        self.setMinimumHeight(200)
        self.setMaximumHeight(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Initialize empty data line
        self._data_line = self.plot(
            pen=mkPen(colors.SECONDARY, width=2),
            symbol='o',
            symbolSize=6,
            symbolBrush=colors.SECONDARY,
            symbolPen=mkPen(colors.TEXT_PRIMARY, width=1)
        )

        # Overlay a truthful empty state rather than drawing invented activity.
        overlay = QVBoxLayout(self)
        overlay.setContentsMargins(64, 24, 24, 24)
        self.empty_label = QLabel("No sync activity yet\nCompleted runs will appear here.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet(f"background: transparent; color: {colors.TEXT_SECONDARY};")
        self.empty_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        overlay.addWidget(self.empty_label)

    def set_data(self, x, y):
        """
        Update the chart with new data.
        Args:
            x: List of x-values (typically time points)
            y: List of y-values (typically sync counts or similar)
        """
        if not x or not y or len(x) != len(y):
            # Clear data if invalid
            self._data_line.setData([], [])
            self.empty_label.show()
            return

        self._data_line.setData(x, y)
        self.empty_label.hide()

    def clear_data(self):
        """Clear all data from the chart."""
        self._data_line.setData([], [])
        self.empty_label.show()
